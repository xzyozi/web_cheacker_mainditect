import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, call, patch

import aiohttp
from playwright.async_api import Browser, BrowserContext, Page
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import pytest

from content_extractor import playwright_helpers
from content_extractor.playwright_helpers import (
    _UNIQUE_SELECTOR_JS,
    ROBOTS_FETCH_TIMEOUT_SECONDS,
    _cleanup_setup_resources,
    adjust_page_view,
    close_page,
    ensure_unique_selector,
    fetch_robots_txt,
    generate_filename,
    is_scraping_allowed,
    is_url_allowed,
    save_screenshot,
    setup_page,
)

# --- Fixtures for Playwright and Aiohttp Mocks ---


@pytest.fixture
def mock_browser():
    return AsyncMock(spec=Browser)


@pytest.fixture
def mock_context(mock_browser):
    context = AsyncMock(spec=BrowserContext)
    mock_browser.new_context.return_value = context
    return context


@pytest.fixture
def mock_page(mock_context):
    page = AsyncMock(spec=Page)
    mock_context.new_page.return_value = page
    return page


@pytest.fixture
def mock_aiohttp_response():
    response = AsyncMock()
    response.status = 200
    response.text.return_value = "User-agent: *\nAllow: /"
    return response


@pytest.fixture(autouse=True)
def mock_asyncio_sleep(mocker):
    # Patch asyncio.sleep to prevent actual delays during tests
    return mocker.patch("asyncio.sleep", new=AsyncMock())


@pytest.fixture(autouse=True)
def allow_all_urls(mocker):
    """save_screenshot が呼ぶ is_url_allowed が、テスト中に実ネットワークへ robots.txt を取りに行かないようにする。

    is_url_allowed 自体のテストは、import 済みの関数オブジェクトを直接呼ぶため、この差し替えの影響を受けない。
    """
    return mocker.patch.object(playwright_helpers, "is_url_allowed", new=AsyncMock(return_value=True))


@pytest.fixture(autouse=True)
def clear_robots_cache():
    playwright_helpers._ROBOTS_CACHE.clear()
    yield
    playwright_helpers._ROBOTS_CACHE.clear()


# --- Tests for setup_page ---


@pytest.mark.asyncio
async def test_setup_page_normal_operation(mock_browser, mock_context, mock_page, mocker):
    """Test Case 1: 正常なページセットアップ。"""
    url = "http://example.com"
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    result_page = await setup_page(url, mock_browser)

    assert result_page is mock_page
    mock_browser.new_context.assert_called_once()
    mock_context.new_page.assert_called_once()
    mock_page.goto.assert_called_once_with(url, wait_until="domcontentloaded", timeout=10000)
    mock_page.wait_for_selector.assert_called_once_with("body", state="attached", timeout=10000)
    mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=15000)


@pytest.mark.asyncio
async def test_setup_page_goto_timeout(mock_browser, mock_context, mock_page, mocker):
    """Test Case 2: `goto`または`wait_for_selector`でのタイムアウト。"""
    url = "http://example.com"
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.side_effect = PlaywrightTimeoutError("Navigation timeout")

    result_page = await setup_page(url, mock_browser)

    assert result_page is None
    mock_page.goto.assert_called_once()
    mock_page.close.assert_awaited_once()  # Page should be closed on failure
    mock_context.close.assert_awaited_once()  # Context should also be closed on failure


@pytest.mark.asyncio
async def test_setup_page_wait_for_load_state_timeout_warns_but_returns_page(
    mock_browser, mock_context, mock_page, mocker
):
    """Test Case 3: `wait_for_load_state`でのタイムアウト。"""
    url = "http://example.com"
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.wait_for_load_state.side_effect = PlaywrightTimeoutError("Load state timeout")

    # Mock logger to check for warning
    mock_logger_warning = mocker.patch("content_extractor.playwright_helpers.logger.warning")

    result_page = await setup_page(url, mock_browser)

    assert result_page is mock_page  # Page should still be returned
    mock_page.wait_for_load_state.assert_called_once()
    mock_logger_warning.assert_called_once()
    mock_context.close.assert_not_called()  # Context should NOT be closed


@pytest.mark.asyncio
async def test_setup_page_other_exception(mock_browser, mock_context, mock_page, mocker):
    """Test Case 4: PlaywrightError 発生時はログに記録してリソースを解放し None を返す。"""
    url = "http://example.com"
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.side_effect = PlaywrightError("Some other error")

    # Mock logger to check for error
    mock_logger_error = mocker.patch("content_extractor.playwright_helpers.logger.error")

    result_page = await setup_page(url, mock_browser)

    assert result_page is None
    mock_page.goto.assert_called_once()
    mock_logger_error.assert_called_once()
    mock_page.close.assert_awaited_once()  # Page should be closed on failure
    mock_context.close.assert_awaited_once()  # Context should also be closed on failure


@pytest.mark.asyncio
async def test_setup_page_reraises_unexpected_exception(mock_browser, mock_context, mock_page, mocker):
    """予期せぬ例外はリソース解放とログ記録のうえ再送出する。"""
    url = "http://example.com"
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.side_effect = RuntimeError("unexpected")
    mock_logger_exception = mocker.patch("content_extractor.playwright_helpers.logger.exception")

    with pytest.raises(RuntimeError, match="unexpected"):
        await setup_page(url, mock_browser)

    mock_logger_exception.assert_called_once()
    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_page_closes_context_when_new_page_fails(mock_browser, mock_context):
    """new_page() が失敗しても作成済みの context はクローズして None を返す。"""
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.side_effect = PlaywrightError("new_page failed")

    result_page = await setup_page("http://example.com", mock_browser)

    assert result_page is None
    mock_context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_page_closes_context_even_when_page_close_fails(mock_browser, mock_context, mock_page, mocker):
    """goto 失敗後の page.close() が PlaywrightError を出しても context.close() が呼ばれ例外は漏れない。"""
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.side_effect = PlaywrightError("goto failed")
    mock_page.close.side_effect = PlaywrightError("page close failed")
    mock_logger_warning = mocker.patch("content_extractor.playwright_helpers.logger.warning")

    result_page = await setup_page("http://example.com", mock_browser)

    assert result_page is None
    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()
    mock_logger_warning.assert_called_once()


# --- Tests for _cleanup_setup_resources ---


@pytest.mark.asyncio
async def test_cleanup_setup_resources_closes_both_page_and_context(mock_page, mock_context):
    """page と context の両方が渡された場合、両方独立してクローズする。"""
    await _cleanup_setup_resources(mock_page, mock_context)

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_setup_resources_closes_context_when_page_is_none(mock_context):
    """page が None の場合でも context をクローズする。"""
    await _cleanup_setup_resources(None, mock_context)

    mock_context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_setup_resources_closes_context_when_page_close_fails(mock_page, mock_context, mocker):
    """page.close() が PlaywrightError を送出しても context.close() を実行し例外を漏らさない。"""
    mock_page.close.side_effect = PlaywrightError("page close error")
    mock_logger_warning = mocker.patch("content_extractor.playwright_helpers.logger.warning")

    await _cleanup_setup_resources(mock_page, mock_context)

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()
    mock_logger_warning.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_setup_resources_logs_warning_when_both_closes_fail(mock_page, mock_context, mocker):
    """page.close() と context.close() の両方が失敗しても警告ログを記録し例外を送出しない。"""
    mock_page.close.side_effect = PlaywrightError("page close error")
    mock_context.close.side_effect = PlaywrightError("context close error")
    mock_logger_warning = mocker.patch("content_extractor.playwright_helpers.logger.warning")

    await _cleanup_setup_resources(mock_page, mock_context)

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()
    assert mock_logger_warning.call_count == 2


# --- Tests for close_page ---


@pytest.mark.asyncio
async def test_close_page_closes_page_and_context(mock_page):
    """ページを閉じた後、そのブラウザコンテキストも閉じる（コンテキストのリーク防止）。"""
    # spec 付きの AsyncMock では、プロパティ context は MagicMock になるため、明示的に差し替える
    mock_context = AsyncMock(spec=BrowserContext)
    mock_page.context = mock_context

    await close_page(mock_page)

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_page_does_not_raise_when_close_fails(mock_page, mocker):
    """page.close() が失敗しても context.close() を試行し、後続のURL処理を止めない。"""
    mock_context = AsyncMock(spec=BrowserContext)
    mock_page.context = mock_context
    mock_page.close.side_effect = PlaywrightError("target closed")
    mock_logger_warning = mocker.patch("content_extractor.playwright_helpers.logger.warning")

    await close_page(mock_page)  # 例外を送出しない

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()
    mock_logger_warning.assert_called_once()


@pytest.mark.asyncio
async def test_close_page_does_not_raise_when_context_close_fails(mock_page, mocker):
    """context.close() が失敗しても警告ログのみ記録し、例外を送出しない。"""
    mock_context = AsyncMock(spec=BrowserContext)
    mock_context.close.side_effect = PlaywrightError("context closed")
    mock_page.context = mock_context
    mock_logger_warning = mocker.patch("content_extractor.playwright_helpers.logger.warning")

    await close_page(mock_page)

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()
    mock_logger_warning.assert_called_once()


# --- Tests for ensure_unique_selector ---

RECT = {"x": 0, "y": 0, "width": 10, "height": 10}


@pytest.mark.asyncio
async def test_ensure_unique_selector_keeps_selector_when_unique(mock_page):
    """ヒットが1件のセレクタは、そのまま使う。"""
    mock_page.evaluate.return_value = {"count": 1, "path": "html > body > div:nth-of-type(1)"}

    assert await ensure_unique_selector(mock_page, "div.card", RECT) == "div.card"


@pytest.mark.asyncio
async def test_ensure_unique_selector_replaces_with_path_when_duplicated(mock_page):
    """複数ヒットのときは、位置が一致した要素の nth-of-type パスに置き換える。"""
    path = "html > body > div:nth-of-type(2)"
    mock_page.evaluate.return_value = {"count": 3, "path": path}

    assert await ensure_unique_selector(mock_page, "div.card", RECT) == path


@pytest.mark.asyncio
async def test_ensure_unique_selector_keeps_selector_when_position_not_matched(mock_page):
    """位置が一致する要素が見つからないときは、元のセレクタを返す（挙動を悪化させない）。"""
    mock_page.evaluate.return_value = {"count": 3, "path": None}

    assert await ensure_unique_selector(mock_page, "div.card", RECT) == "div.card"


@pytest.mark.asyncio
async def test_ensure_unique_selector_keeps_selector_when_evaluate_fails(mock_page):
    """JavaScript の評価に失敗しても、例外を出さず元のセレクタを返す。"""
    mock_page.evaluate.side_effect = PlaywrightError("boom")

    assert await ensure_unique_selector(mock_page, "div.card", RECT) == "div.card"


@pytest.mark.asyncio
async def test_ensure_unique_selector_ignores_unexpected_result(mock_page):
    """戻り値が辞書でない（モックなど）場合は、元のセレクタを返す。"""
    mock_page.evaluate.return_value = "unexpected"

    assert await ensure_unique_selector(mock_page, "div.card", RECT) == "div.card"


@pytest.mark.asyncio
async def test_ensure_unique_selector_empty_selector(mock_page):
    """空のセレクタは、ページを評価せずそのまま返す。"""
    assert await ensure_unique_selector(mock_page, "", RECT) == ""
    mock_page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_unique_selector_uses_viewport_coordinates(mock_page):
    """_UNIQUE_SELECTOR_JS はスクロール量を加算せず、ビューポート相対座標をそのまま比較する。"""
    rect = {"x": 120.5, "y": -300.0, "width": 400.0, "height": 240.0}
    mock_page.evaluate.return_value = {"count": 2, "path": "html > body:nth-of-type(1) > div:nth-of-type(2)"}

    result = await ensure_unique_selector(mock_page, "div.card", rect)

    assert result == "html > body:nth-of-type(1) > div:nth-of-type(2)"
    mock_page.evaluate.assert_awaited_once_with(_UNIQUE_SELECTOR_JS, {"selector": "div.card", "rect": rect})
    assert "scrollX" not in _UNIQUE_SELECTOR_JS
    assert "scrollY" not in _UNIQUE_SELECTOR_JS
    assert "near(r.x, rect.x)" in _UNIQUE_SELECTOR_JS
    assert "near(r.y, rect.y)" in _UNIQUE_SELECTOR_JS


# --- Tests for adjust_page_view ---


@pytest.mark.asyncio
async def test_adjust_page_view_correctly_sets_viewport_and_scrolls(mock_page, mocker):
    """Test Case 1: 正しいビューポートサイズ設定とスクロール。"""
    mocker.patch("content_extractor.playwright_helpers.asyncio.sleep", new=AsyncMock())  # Ensure sleep is mocked

    # Mock page.evaluate to return document dimensions
    mock_page.evaluate.side_effect = [
        {"width": 1000, "height": 2000, "scrollWidth": 1000, "scrollHeight": 3000},  # First call for dimensions
        None,  # Second call for scrolling (return value doesn't matter)
    ]

    dimensions = await adjust_page_view(mock_page)

    assert mock_page.evaluate.call_count == 2
    mock_page.set_viewport_size.assert_called_once_with({"width": 1000, "height": 2000})
    mock_page.evaluate.assert_has_calls(
        [
            call("""() => {
        return {
            width: Math.max(document.body.scrollWidth, document.body.offsetWidth,
                            document.documentElement.clientWidth, document.documentElement.scrollWidth,
                            document.documentElement.offsetWidth),
            height: Math.max(document.body.scrollHeight, document.body.offsetHeight,
                             document.documentElement.clientHeight, document.documentElement.scrollHeight,
                             document.documentElement.offsetHeight)
        }
    }"""),
            call("window.scrollTo(0, document.body.scrollHeight)"),
        ]
    )
    assert dimensions == {"width": 1000, "height": 2000, "scrollWidth": 1000, "scrollHeight": 3000}


# --- Tests for fetch_robots_txt ---


@pytest.mark.asyncio
@patch("content_extractor.playwright_helpers.aiohttp.ClientSession")
async def test_fetch_robots_txt_success(MockClientSession, mock_aiohttp_response):
    """Test Case 1: 正常な`robots.txt`の取得"""
    # Arrange
    get_context = AsyncMock()
    get_context.__aenter__.return_value = mock_aiohttp_response
    session = MagicMock()
    session.get.return_value = get_context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    # Act
    url = "http://example.com/some/path"
    robots_content = await fetch_robots_txt(url)

    # Assert
    assert robots_content == "User-agent: *\nAllow: /"
    session.get.assert_called_once_with("http://example.com/robots.txt")


@pytest.mark.asyncio
@patch("content_extractor.playwright_helpers.aiohttp.ClientSession")
async def test_fetch_robots_txt_not_found(MockClientSession, mock_aiohttp_response):
    """Test Case 2: `robots.txt`が見つからない (404)"""
    # Arrange
    mock_aiohttp_response.status = 404
    get_context = AsyncMock()
    get_context.__aenter__.return_value = mock_aiohttp_response
    session = MagicMock()
    session.get.return_value = get_context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    # Act
    url = "http://example.com/some/path"
    robots_content = await fetch_robots_txt(url)

    # Assert
    assert robots_content is None
    session.get.assert_called_once()


@pytest.mark.asyncio
@patch("content_extractor.playwright_helpers.aiohttp.ClientSession")
async def test_fetch_robots_txt_network_error(MockClientSession):
    """Test Case 3: ネットワークエラー"""
    # Arrange: session.get() will raise a ClientError
    session = MagicMock()
    session.get.side_effect = aiohttp.ClientError("Network Error")
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    # Act
    url = "http://example.com/some/path"
    robots_content = await fetch_robots_txt(url)

    # Assert
    assert robots_content is None
    session.get.assert_called_once()


@pytest.mark.asyncio
@patch("content_extractor.playwright_helpers.aiohttp.ClientSession")
async def test_fetch_robots_txt_timeout_error(MockClientSession):
    """robots.txt 取得時の asyncio.TimeoutError では None を返す。"""
    session = MagicMock()
    session.get.side_effect = asyncio.TimeoutError("Request timeout")
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    robots_content = await fetch_robots_txt("http://example.com/some/path")

    assert robots_content is None
    session.get.assert_called_once()


@pytest.mark.asyncio
@patch("content_extractor.playwright_helpers.aiohttp.ClientSession")
async def test_fetch_robots_txt_sets_client_timeout(MockClientSession, mock_aiohttp_response):
    """robots.txt 取得時に aiohttp.ClientSession へ明示的な ClientTimeout を渡す。"""
    get_context = AsyncMock()
    get_context.__aenter__.return_value = mock_aiohttp_response
    session = MagicMock()
    session.get.return_value = get_context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    MockClientSession.return_value = session_context

    await fetch_robots_txt("http://example.com/some/path")

    MockClientSession.assert_called_once_with(timeout=aiohttp.ClientTimeout(total=ROBOTS_FETCH_TIMEOUT_SECONDS))


# --- Tests for is_scraping_allowed ---


def test_is_scraping_allowed_allowed_path():
    """Test Case 1: 許可されているパス"""
    robots_txt = "User-agent: *\nDisallow: /admin\nAllow: /public"
    assert is_scraping_allowed(robots_txt, "/public/page") is True
    assert is_scraping_allowed(robots_txt, "/another/path") is True  # Not explicitly disallowed


def test_is_scraping_allowed_disallowed_path():
    """Test Case 2: 禁止されているパス"""
    robots_txt = "User-agent: *\nDisallow: /private\nDisallow: /temp"
    assert is_scraping_allowed(robots_txt, "/private/data") is False
    assert is_scraping_allowed(robots_txt, "/temp/file.html") is False


def test_is_scraping_allowed_empty_robots_txt():
    """Test Case 3: `robots.txt`が存在しない（空の文字列）"""
    robots_txt = ""
    assert is_scraping_allowed(robots_txt, "/any/path") is True
    assert is_scraping_allowed(robots_txt, "/admin") is True


def test_is_scraping_allowed_comment_and_empty_lines():
    """Test Case 4: コメント行と空行の処理"""
    robots_txt = """
# This is a comment
User-agent: *

Disallow: /secret
"""
    assert is_scraping_allowed(robots_txt, "/secret/page") is False
    assert is_scraping_allowed(robots_txt, "/public/page") is True


# --- Tests for is_url_allowed ---


@pytest.mark.asyncio
async def test_is_url_allowed_disallowed_path(mocker):
    """robots.txt が禁止しているパスは許可されない。"""
    mocker.patch.object(
        playwright_helpers, "fetch_robots_txt", new=AsyncMock(return_value="User-agent: *\nDisallow: /private")
    )

    assert await is_url_allowed("http://example.com/private/data") is False
    assert await is_url_allowed("http://example.com/public/page") is True


@pytest.mark.asyncio
async def test_is_url_allowed_fetches_robots_once_per_origin(mocker):
    """同じオリジンへの判定では、robots.txt を1回しか取得しない（アクセス回数の削減）。"""
    fetch = mocker.patch.object(
        playwright_helpers, "fetch_robots_txt", new=AsyncMock(return_value="User-agent: *\nAllow: /")
    )

    await is_url_allowed("http://example.com/a")
    await is_url_allowed("http://example.com/b")
    await is_url_allowed("http://other.example.org/a")

    assert fetch.await_count == 2  # example.com と other.example.org の2オリジン


@pytest.mark.asyncio
async def test_is_url_allowed_caches_fetch_failure(mocker):
    """robots.txt が取得できない場合は許可し、失敗も含めて再取得しない。"""
    fetch = mocker.patch.object(playwright_helpers, "fetch_robots_txt", new=AsyncMock(return_value=None))

    assert await is_url_allowed("http://example.com/a") is True
    assert await is_url_allowed("http://example.com/b") is True
    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_is_url_allowed_invalid_url_is_allowed(mocker):
    """URL を解析できない場合は判定せず許可とする（検証は呼び出し側の責務）。"""
    fetch = mocker.patch.object(playwright_helpers, "fetch_robots_txt", new=AsyncMock())

    assert await is_url_allowed("invalid-url") is True
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_url_allowed_deduplicates_concurrent_requests_same_origin(mocker):
    """同一オリジンへの並列判定でも、遅延中に重複取得せず fetch_robots_txt は1回だけ呼ばれる。"""

    async def delayed_fetch(_url: str) -> str:
        # autouse の mock_asyncio_sleep を避け、イベントループへ確実に制御を譲って並列競合を再現する
        loop = asyncio.get_running_loop()
        ready = loop.create_future()
        loop.call_soon(ready.set_result, None)
        await ready
        return "User-agent: *\nDisallow: /private"

    fetch = mocker.patch.object(playwright_helpers, "fetch_robots_txt", new=AsyncMock(side_effect=delayed_fetch))

    results = await asyncio.gather(
        is_url_allowed("http://example.com/a"),
        is_url_allowed("http://example.com/b"),
        is_url_allowed("http://example.com/private"),
    )

    assert results == [True, True, False]
    assert fetch.await_count == 1


def test_is_url_allowed_works_across_multiple_event_loops(mocker):
    """異なるイベントループをまたいで呼び出してもロックが衝突せず動作する。"""
    fetch = mocker.patch.object(
        playwright_helpers, "fetch_robots_txt", new=AsyncMock(return_value="User-agent: *\nAllow: /")
    )

    assert asyncio.run(is_url_allowed("http://example.com/a")) is True
    playwright_helpers._ROBOTS_CACHE.clear()
    assert asyncio.run(is_url_allowed("http://example.com/b")) is True
    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_save_screenshot_skips_disallowed_url(mock_browser, allow_all_urls, mocker):
    """robots.txt で許可されていない URL は、ブラウザを開かず None を返す。"""
    mocker.patch("os.makedirs")
    allow_all_urls.return_value = False  # 既定の「許可」を、このテストだけ「禁止」に切り替える

    result = await save_screenshot(mock_browser, ["http://example.com/private"])

    assert result == [None]
    mock_browser.new_context.assert_not_called()


# --- Tests for generate_filename ---


def test_generate_filename_basic_url():
    """Test Case 1: 基本的なURLからの生成"""
    url = "https://example.com/some/path/page.html"
    filename = generate_filename(url)
    assert filename.startswith("example_com_page.html_")
    assert filename.endswith(".png")
    assert len(filename) > len("example_com_page.html_.png")  # Check for hash


def test_generate_filename_url_with_query_params():
    """Test Case 2: クエリパラメータを含むURL"""
    url = "https://example.com/page?param=value&id=123"
    filename = generate_filename(url)
    assert filename.startswith("example_com_page_")
    assert filename.endswith(".png")
    # Should not contain query params in the readable part
    assert "param" not in filename and "value" not in filename


def test_generate_filename_url_with_special_characters():
    """Test Case 3: 特殊文字を含むURL"""
    url = "https://example.com/path/with spaces/file!.html"
    filename = generate_filename(url)
    # The actual generated part will have 'file!.html' as last_part, and spaces from the original path
    # will implicitly be handled by the URL parsing and hash generation.
    assert filename.startswith("example_com_file!.html_")  # `last_part` directly includes "file!.html"
    # Spaces are removed during domain processing, but here we check for the original full URL's
    # path part in the filename before hash.
    # The `path_hash` is based on the full path which would include spaces, but `last_part` itself is just 'file!.html'
    # The `domain` part has `_` for `.`, but the `last_part` does not replace spaces with `_`.
    # Let's adjust this to accurately reflect generated string.
    # The `path` for "/path/with spaces/file!.html" is what gets hashed.
    # The `last_part` is "file!.html".
    # The `domain` is "example_com".
    # So the expected prefix is "example_com_file!.html_"
    assert " " not in filename  # The filename string itself will not contain literal spaces due to hashing.
    assert filename.endswith(".png")


def test_generate_filename_root_url():
    """Test Case 4: ルートURL"""
    url = "https://example.com"
    filename = generate_filename(url)
    assert filename.startswith("example_com_index_")
    assert filename.endswith(".png")


def test_generate_filename_url_with_trailing_slash():
    """URLが末尾スラッシュを持つ場合のテスト"""
    url = "https://anothersite.org/my/page/"
    filename = generate_filename(url)
    assert filename.startswith("anothersite_org_page_")
    assert filename.endswith(".png")


# --- Tests for save_screenshot (complex, will need more specific mocks) ---


@pytest.mark.asyncio
@patch("os.makedirs")
@patch("os.path.join", side_effect=os.path.join)  # Keep original behavior for path joining
@patch("PIL.Image.open")
async def test_save_screenshot_success(
    mock_image_open, mock_path_join, mock_makedirs, mock_browser, mock_context, mock_page, mock_asyncio_sleep
):
    """Test Case 1: 正常なスクリーンショットの保存とリサイズ"""
    url = "http://example.com/test"
    test_filepath = os.path.join("temp", generate_filename(url))

    # Mock Playwright calls
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.return_value = None
    mock_page.screenshot.return_value = None

    # Mock PIL.Image calls
    mock_img_instance = MagicMock()
    mock_img_instance.width = 1000
    mock_img_instance.height = 500
    mock_image_open.return_value.__enter__.return_value = mock_img_instance
    mock_img_instance.resize.return_value = mock_img_instance  # Resized image is the same mock
    mock_img_instance.save.return_value = None

    result_paths = await save_screenshot(mock_browser, [url], width=200)

    mock_makedirs.assert_called_once_with("temp", exist_ok=True)
    mock_browser.new_context.assert_called_once()
    mock_context.new_page.assert_called_once()
    mock_page.goto.assert_called_once_with(url, wait_until="load", timeout=30000)
    mock_page.screenshot.assert_called_once_with(path=test_filepath, full_page=True)
    mock_image_open.assert_called_once_with(test_filepath)
    # Expected resize: width=200, height= (200 * 500/1000) = 100
    mock_img_instance.resize.assert_called_once_with((200, 100))
    mock_img_instance.save.assert_called_once_with(test_filepath)
    mock_page.close.assert_called_once()
    mock_context.close.assert_called_once()
    assert result_paths == [test_filepath]
    assert mock_asyncio_sleep.call_count == 0


@pytest.mark.asyncio
@patch("os.makedirs")
@patch("os.path.join", side_effect=os.path.join)
@patch("PIL.Image.open")
async def test_save_screenshot_invalid_url(
    mock_image_open, mock_path_join, mock_makedirs, mock_browser, mock_asyncio_sleep
):
    """Test Case 2: 無効なURLのスキップ"""
    invalid_url = "invalid-url"
    result_paths = await save_screenshot(mock_browser, [invalid_url])
    assert result_paths == [None]
    mock_makedirs.assert_called_once()  # Should still try to make dir
    mock_browser.new_context.assert_not_called()
    assert mock_asyncio_sleep.call_count == 0


@pytest.mark.asyncio
@patch("os.makedirs")
@patch("os.path.join", side_effect=os.path.join)
@patch("PIL.Image.open")
async def test_save_screenshot_retry_on_timeout(
    mock_image_open, mock_path_join, mock_makedirs, mock_browser, mock_context, mock_page, mock_asyncio_sleep
):
    """Test Case 3: リトライメカニズム (PlaywrightTimeoutError)"""
    url = "http://example.com/retry"
    test_filepath = os.path.join("temp", generate_filename(url))

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Fail twice, succeed on third attempt
    mock_page.goto.side_effect = [
        PlaywrightTimeoutError("timeout 1"),
        PlaywrightTimeoutError("timeout 2"),
        None,  # Success on third try
    ]
    mock_page.screenshot.return_value = None

    mock_img_instance = MagicMock()
    mock_img_instance.width = 1000
    mock_img_instance.height = 500
    mock_image_open.return_value.__enter__.return_value = mock_img_instance
    mock_img_instance.resize.return_value = mock_img_instance
    mock_img_instance.save.return_value = None

    result_paths = await save_screenshot(mock_browser, [url])

    assert result_paths == [test_filepath]
    assert mock_browser.new_context.call_count == 3
    assert mock_context.new_page.call_count == 3
    assert mock_page.goto.call_count == 3
    assert mock_page.screenshot.call_count == 1  # Only called on success
    assert mock_asyncio_sleep.call_count == 2  # Sleep after first two failures


@pytest.mark.asyncio
@patch("os.makedirs")
@patch("os.path.join", side_effect=os.path.join)
@patch("PIL.Image.open")
async def test_save_screenshot_max_retries_exceeded(
    mock_image_open, mock_path_join, mock_makedirs, mock_browser, mock_context, mock_page, mock_asyncio_sleep
):
    """Test Case 4: 最大リトライ回数を超えた失敗"""
    url = "http://example.com/fail"

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Always fail
    mock_page.goto.side_effect = PlaywrightTimeoutError("timeout")

    result_paths = await save_screenshot(mock_browser, [url])

    assert result_paths == [None]
    assert mock_browser.new_context.call_count == 3
    assert mock_context.new_page.call_count == 3
    assert mock_page.goto.call_count == 3
    assert mock_page.screenshot.call_count == 0
    assert mock_asyncio_sleep.call_count == 2


@pytest.mark.asyncio
@patch("os.makedirs")
@patch("os.path.join", side_effect=os.path.join)
@patch("PIL.Image.open")
async def test_save_screenshot_aspect_ratio(
    mock_image_open, mock_path_join, mock_makedirs, mock_browser, mock_context, mock_page
):
    """Test Case 5: 画像リサイズ時のアスペクト比保持"""
    url = "http://example.com/aspect"

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.return_value = None
    mock_page.screenshot.return_value = None

    mock_img_instance = MagicMock()
    mock_img_instance.width = 1200
    mock_img_instance.height = 600  # Aspect ratio 2:1
    mock_image_open.return_value.__enter__.return_value = mock_img_instance
    mock_img_instance.resize.return_value = mock_img_instance
    mock_img_instance.save.return_value = None

    # Test with only width specified
    await save_screenshot(mock_browser, [url], width=300, height=None)
    mock_img_instance.resize.assert_called_once_with((300, 150))  # height should be 300 / 2 = 150

    mock_img_instance.resize.reset_mock()  # Reset for second assertion
    # Test with both width and height specified (height should override aspect ratio)
    await save_screenshot(mock_browser, [url], width=300, height=400)
    mock_img_instance.resize.assert_called_once_with((300, 400))


@pytest.mark.asyncio
@patch("os.makedirs")
@patch("os.path.join", side_effect=os.path.join)
@patch("PIL.Image.open")
async def test_save_screenshot_makedirs_called(
    mock_image_open, mock_path_join, mock_makedirs, mock_browser, mock_context, mock_page
):
    """Test Case 6: ディレクトリの作成"""
    url = "http://example.com/makedirs"

    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.return_value = None
    mock_page.screenshot.return_value = None
    mock_image_open.return_value.__enter__.return_value = MagicMock()  # Minimal mock for image operations

    await save_screenshot(mock_browser, [url], save_dir="new_temp_dir")
    mock_makedirs.assert_called_once_with("new_temp_dir", exist_ok=True)


@pytest.mark.asyncio
@patch("os.makedirs")
async def test_save_screenshot_playwright_error_retries_and_returns_none(
    mock_makedirs, mock_browser, mock_context, mock_page, mock_asyncio_sleep
):
    """PlaywrightError 時はリトライし、最大回数超過で None を返す。"""
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.side_effect = PlaywrightError("navigation error")

    result = await save_screenshot(mock_browser, ["http://example.com/err"])

    assert result == [None]
    assert mock_page.goto.call_count == 3
    assert mock_asyncio_sleep.call_count == 2


@pytest.mark.asyncio
@patch("os.makedirs")
async def test_save_screenshot_reraises_unexpected_exception(mock_makedirs, mock_browser, mock_context, mock_page):
    """予期せぬ例外はリトライや握りつぶしをせず、リソース解放して再送出する。"""
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.goto.side_effect = RuntimeError("unexpected bug")

    with pytest.raises(RuntimeError, match="unexpected bug"):
        await save_screenshot(mock_browser, ["http://example.com/bug"])

    mock_page.close.assert_awaited_once()
    mock_context.close.assert_awaited_once()
