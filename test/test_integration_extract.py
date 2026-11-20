"""実ブラウザ（Chromium）を使う結合テスト。

ローカルの HTTP サーバーで固定の HTML を配信し、`extract_main_content` / `quick_extract_content` を
`make_tree` からスコアリングまで通して検証する。モックを使う単体テストでは見つけられない、
スコアリングや Quick スキャンの不具合を検出するのが目的。

Chromium が未導入の環境では、このファイルのテストはスキップされる。
CI では `playwright install --with-deps chromium` で導入している。
実行: `pytest -m integration` / 除外: `pytest -m "not integration"`
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading

from playwright.async_api import async_playwright
import pytest
import pytest_asyncio

from content_extractor import playwright_helpers
from content_extractor.core import extract_main_content, quick_extract_content

pytestmark = pytest.mark.integration

ARTICLE_COUNT = 8


def build_page(link_prefix: str = "/article/") -> str:
    """ナビ・本文（記事一覧）・フッターを持つ、固定の一覧ページ。

    本文だけが `link_prefix` で始まるリンクを持つ。ナビとフッターは別のプレフィックスにして、
    抽出結果にナビやフッターのリンクが混ざらないことを検証できるようにする。
    """
    articles = "\n".join(
        f"""
        <article>
          <h2><a href="{link_prefix}{i}.html">記事タイトル {i}</a></h2>
          <p>これは記事 {i} の本文です。メインコンテンツとして判定されるよう、ある程度の長さの文章を入れておきます。</p>
        </article>"""
        for i in range(ARTICLE_COUNT)
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>テストページ</title>
  <style>
    body {{ margin: 0; font-family: sans-serif; }}
    header {{ height: 80px; background: #eee; }}
    nav a {{ display: inline-block; margin: 20px; }}
    main {{ width: 70%; margin: 20px auto; min-height: 600px; }}
    article {{ margin-bottom: 24px; }}
    footer {{ height: 60px; background: #ddd; }}
  </style>
</head>
<body>
  <header><nav>
    <a href="/nav/home.html">ホーム</a>
    <a href="/nav/about.html">概要</a>
    <a href="/nav/contact.html">連絡先</a>
  </nav></header>
  <main>{articles}
  </main>
  <footer><a href="/footer/terms.html">利用規約</a></footer>
</body>
</html>
"""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass


@pytest.fixture
def site(tmp_path):
    """tmp_path を配信するローカル HTTP サーバー。`(base_url, root_path)` を返す。

    robots.txt は既定では存在しない（404）。
    """
    handler = partial(_QuietHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


@pytest_asyncio.fixture
async def browser():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:  # Chromium 未導入など
            pytest.skip(f"Chromium を起動できないためスキップ: {e}")
        try:
            yield browser
        finally:
            await browser.close()


@pytest.fixture(autouse=True)
def isolate(mocker):
    # URL のドメイン（127.0.0.1:ポート）はファイル名に使えない環境があるため、保存はしない
    mocker.patch("content_extractor.core.save_json")
    playwright_helpers._ROBOTS_CACHE.clear()
    yield
    playwright_helpers._ROBOTS_CACHE.clear()


@pytest.mark.asyncio
async def test_full_scan_extracts_article_links_only(browser, site):
    """Full スキャンが、本文（記事）のリンクだけを抽出し、ナビやフッターのリンクを含めない。"""
    base_url, root = site
    (root / "index.html").write_text(build_page(), encoding="utf-8")

    result = await extract_main_content(f"{base_url}/index.html", browser)

    assert result is not None
    assert result.links, "リンクが1件も抽出されていない"
    assert all("/article/" in link for link in result.links), f"本文以外のリンクが混ざっている: {result.links}"
    assert result.css_selector, "セレクタが生成されていない"


@pytest.mark.asyncio
async def test_quick_scan_reuses_selector_from_full_scan(browser, site):
    """Full スキャンで得たセレクタを使った Quick スキャンが、同じページで同じリンクを返す。"""
    base_url, root = site
    (root / "index.html").write_text(build_page(), encoding="utf-8")
    url = f"{base_url}/index.html"

    full = await extract_main_content(url, browser)
    assert full is not None

    quick = await quick_extract_content(url, browser, list(full.css_selector_list), full.web_type)

    assert quick is not None, f"保存したセレクタで要素を取得できなかった: {full.css_selector_list}"
    assert quick.links == full.links


@pytest.mark.asyncio
async def test_quick_scan_detects_changed_links(browser, site):
    """本文のリンクが変わったとき、Quick スキャンの結果のリンクが変わる（更新の検知の前提）。"""
    base_url, root = site
    page = root / "index.html"
    page.write_text(build_page("/article/"), encoding="utf-8")
    url = f"{base_url}/index.html"

    full = await extract_main_content(url, browser)
    assert full is not None

    page.write_text(build_page("/article-v2/"), encoding="utf-8")
    quick = await quick_extract_content(url, browser, list(full.css_selector_list), full.web_type)

    assert quick is not None
    assert quick.links != full.links
    assert all("/article-v2/" in link for link in quick.links)


@pytest.mark.asyncio
async def test_robots_txt_disallow_blocks_full_and_quick_scan(browser, site):
    """robots.txt で禁止されたパスは、Full スキャンでも Quick スキャンでもアクセスしない。"""
    base_url, root = site
    (root / "robots.txt").write_text("User-agent: *\nDisallow: /private/\n", encoding="utf-8")
    private = root / "private"
    private.mkdir()
    (private / "index.html").write_text(build_page(), encoding="utf-8")
    url = f"{base_url}/private/index.html"

    assert await extract_main_content(url, browser) is None
    assert await quick_extract_content(url, browser, ["main"], "plane") is None
