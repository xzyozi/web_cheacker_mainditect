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

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
import pytest
import pytest_asyncio

from content_extractor import core as content_extractor_core
from content_extractor import playwright_helpers
from content_extractor.core import extract_main_content, quick_extract_content
from content_extractor.make_tree import make_tree

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
        except (PlaywrightError, OSError) as e:  # Chromium 未導入など
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


def build_duplicate_class_page(extra_style: str = "", body_prefix: str = "") -> str:
    """同じクラス名（`card`）を持つ兄弟要素が複数ある一覧ページ。

    `div.card` のようなタグとクラスだけのセレクタは、3件すべてにヒットしてしまう。
    """
    cards = "\n".join(
        f"""
    <div class="card">
      <h2><a href="/card/{i}.html">カード {i}</a></h2>
      <p>これはカード {i} の本文です。メインコンテンツとして判定されるよう、ある程度の長さの文章を入れておきます。</p>
    </div>"""
        for i in range(3)
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>重複クラスのページ</title>
  <style>
    body {{ margin: 0; font-family: sans-serif; }}
    .card {{ width: 60%; margin: 20px auto; min-height: 240px; }}
    {extra_style}
  </style>
</head>
<body>{body_prefix}{cards}
</body>
</html>
"""


@pytest.mark.asyncio
async def test_saved_primary_selector_matches_exactly_one_element(browser, site):
    """保存するプライマリセレクタが、ページ内でちょうど1件にヒットする（別の要素を拾わない）。"""
    base_url, root = site
    (root / "index.html").write_text(build_duplicate_class_page(), encoding="utf-8")
    url = f"{base_url}/index.html"

    result = await extract_main_content(url, browser)
    assert result is not None
    assert result.css_selector

    page = await browser.new_page()
    try:
        await page.goto(url)
        hits = await page.locator(result.css_selector).count()
    finally:
        await page.close()

    assert hits == 1, f"セレクタ {result.css_selector!r} が {hits} 件にヒットしている"


def build_scrolled_duplicate_class_page() -> str:
    """`adjust_page_view` 実行後も `window.scrollY > 0` となる、重複クラスを持つ縦長ページ。

    `header` に `100vh` を指定しているため、`adjust_page_view` が初期ページ高に合わせて
    ビューポート高を広げた後に再レイアウトが発生し、`window.scrollTo(0, scrollHeight)` で
    `window.scrollY > 0` になる。
    """
    return build_duplicate_class_page(
        extra_style="header { height: 100vh; background: #eee; }",
        body_prefix="\n  <header></header>",
    )


@pytest.mark.asyncio
async def test_saved_primary_selector_matches_exactly_one_element_on_scrolled_page(browser, site, mocker):
    """スクロール発生ページ（window.scrollY > 0）でも、重複クラスが nth-of-type の一意なセレクタに置き換わる。"""
    base_url, root = site
    (root / "index.html").write_text(build_scrolled_duplicate_class_page(), encoding="utf-8")
    url = f"{base_url}/index.html"

    scroll_ys: list[float] = []
    orig_ensure_unique_selector = content_extractor_core.ensure_unique_selector

    async def spy_ensure_unique_selector(page, selector, rect):
        scroll_ys.append(await page.evaluate("window.scrollY"))
        return await orig_ensure_unique_selector(page, selector, rect)

    mocker.patch.object(content_extractor_core, "ensure_unique_selector", side_effect=spy_ensure_unique_selector)

    result = await extract_main_content(url, browser)
    assert result is not None
    assert result.css_selector
    assert scroll_ys and any(y > 0 for y in scroll_ys), f"スクロールが発生していない: scroll_ys={scroll_ys}"
    assert "nth-of-type(" in result.css_selector, f"重複セレクタが一意化されていない: {result.css_selector!r}"

    page = await browser.new_page()
    try:
        await page.goto(url)
        hits = await page.locator(result.css_selector).count()
    finally:
        await page.close()

    assert hits == 1, f"セレクタ {result.css_selector!r} が {hits} 件にヒットしている"


@pytest.mark.asyncio
async def test_ensure_unique_selector_matches_scrolled_element_from_make_tree(browser, site):
    """window.scrollY > 0 の状態で make_tree が取得した rect と ensure_unique_selector の座標系が一致する。"""
    base_url, root = site
    (root / "index.html").write_text(build_scrolled_duplicate_class_page(), encoding="utf-8")
    url = f"{base_url}/index.html"

    page = await browser.new_page(viewport={"width": 1920, "height": 1080})
    try:
        await page.goto(url)
        await page.evaluate("window.scrollTo(0, 600)")
        scroll_y = await page.evaluate("window.scrollY")
        assert scroll_y > 0

        tree = await make_tree(page, wait_for_load=False)
        assert tree is not None
        card_nodes = [child for child in tree.children if child.css_selector == "div.card"]
        assert len(card_nodes) == 3

        unique_selector = await playwright_helpers.ensure_unique_selector(
            page, card_nodes[1].css_selector, card_nodes[1].rect.to_dict()
        )
        assert "nth-of-type(" in unique_selector
        assert await page.locator(unique_selector).count() == 1
    finally:
        await page.close()


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


@pytest.mark.asyncio
async def test_make_tree_batch_js_skips_hidden_and_supports_single_node_mode(browser, site):
    """#89: 一括 JS 取得で非表示要素を除外し、include_children=False でルート1ノードのみ収集する。"""
    base_url, root = site
    (root / "hidden.html").write_text(
        """<!DOCTYPE html>
<html lang="ja">
<body>
  <main id="target">
    <p><a href="/visible.html">可視リンク</a></p>
    <div style="display: none;"><a href="/hidden.html">非表示リンク</a></div>
  </main>
</body>
</html>""",
        encoding="utf-8",
    )
    url = f"{base_url}/hidden.html"

    page = await browser.new_page(viewport={"width": 1920, "height": 1080})
    try:
        await page.goto(url, wait_until="domcontentloaded")
        full_tree = await make_tree(page, selector="main#target", wait_for_load=False, include_children=True)
        quick_tree = await make_tree(page, selector="main#target", wait_for_load=False, include_children=False)
    finally:
        await page.close()

    assert full_tree is not None
    assert [child.tag for child in full_tree.children] == ["p"]
    assert quick_tree is not None
    assert quick_tree.children == []
    assert any(link.endswith("/visible.html") for link in quick_tree.links)
