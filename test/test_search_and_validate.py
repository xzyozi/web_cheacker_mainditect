"""search_quality.search_and_validate（Google検索結果の妥当性検証）のテスト。"""

from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import Error as PlaywrightError
import pytest

from content_extractor.dom_treeSt import DOMTreeSt
from search_quality import search_and_validate as sv


def _browser_with_links(hrefs):
    """`div.g a[href^="http"]` が指定の href を返すブラウザのモックを作る。"""
    textarea = MagicMock()
    textarea.fill = AsyncMock()
    textarea.press = AsyncMock()

    links = MagicMock()
    links.count = AsyncMock(return_value=len(hrefs))
    links.nth.side_effect = lambda i: MagicMock(get_attribute=AsyncMock(return_value=hrefs[i]))

    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.close = AsyncMock()
    page.locator.side_effect = lambda selector: textarea if "textarea" in selector else links

    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=page)
    return browser, page, textarea


@pytest.mark.asyncio
async def test_search_on_google_returns_unique_urls_in_order_and_skips_empty():
    """重複と空の href を除き、出現順でURLを返す。"""
    browser, page, textarea = _browser_with_links(["https://a.example", "https://b.example", "https://a.example", None])

    urls = await sv.search_on_google(browser, "playwright")

    assert urls == ["https://a.example", "https://b.example"]
    textarea.fill.assert_awaited_once_with("playwright")
    textarea.press.assert_awaited_once_with("Enter")
    page.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_on_google_returns_empty_and_closes_page_on_playwright_error():
    """Playwright のエラーでは空リストを返し、ページは閉じる。"""
    browser, page, _ = _browser_with_links([])
    page.goto.side_effect = PlaywrightError("navigation failed")

    assert await sv.search_on_google(browser, "playwright") == []
    page.close.assert_awaited_once()


def _playwright_manager():
    browser = MagicMock()
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    return manager


def _node(category: str, text: str = "playwright guide", sqs: float = 80.0, empty: bool = False) -> DOMTreeSt:
    node = DOMTreeSt(tag="div", text=text)
    node.quality_category = category
    node.sqs_score = sqs
    node.is_empty_result = empty
    return node


@pytest.mark.asyncio
async def test_main_stops_when_no_search_results():
    """検索結果が無ければ、品質評価を呼ばずに終了する。"""
    with (
        patch.object(sv, "async_playwright", return_value=_playwright_manager()),
        patch.object(sv, "search_on_google", new=AsyncMock(return_value=[])),
        patch.object(sv, "run_search_quality_evaluation_standalone", new=AsyncMock()) as evaluate,
    ):
        await sv.main("playwright")

    evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_main_evaluates_only_top_five_urls():
    """評価対象は検索結果の上位5件に限る。"""
    urls = [f"https://site{i}.example" for i in range(8)]
    with (
        patch.object(sv, "async_playwright", return_value=_playwright_manager()),
        patch.object(sv, "search_on_google", new=AsyncMock(return_value=urls)),
        patch.object(sv, "run_search_quality_evaluation_standalone", new=AsyncMock(return_value=None)) as evaluate,
    ):
        await sv.main("playwright")

    assert [call.args[0] for call in evaluate.await_args_list] == urls[:5]


@pytest.mark.asyncio
async def test_main_selects_only_valid_pages_containing_keyword():
    """Valid かつ本文にキーワードを含むページだけを「妥当」として報告する。"""
    urls = ["https://valid.example", "https://nokeyword.example", "https://low.example", "https://empty.example"]
    results = {
        urls[0]: _node("Valid", text="All about Playwright testing"),
        urls[1]: _node("Valid", text="unrelated text"),
        urls[2]: _node("Low Quality"),
        urls[3]: _node("", empty=True),
    }
    evaluate = AsyncMock(side_effect=lambda url, keyword: results[url])

    with (
        patch.object(sv, "async_playwright", return_value=_playwright_manager()),
        patch.object(sv, "search_on_google", new=AsyncMock(return_value=urls)),
        patch.object(sv, "run_search_quality_evaluation_standalone", new=evaluate),
        patch.object(sv, "logger") as logger,
    ):
        await sv.main("playwright")

    reported = [call.args[0] for call in logger.info.call_args_list if "- URL:" in call.args[0]]
    assert len(reported) == 1
    assert "https://valid.example" in reported[0]


@pytest.mark.asyncio
async def test_main_continues_after_a_url_fails():
    """1URLの評価が例外で失敗しても、残りのURLの評価を続ける。"""
    urls = ["https://broken.example", "https://ok.example"]
    evaluate = AsyncMock(side_effect=[RuntimeError("boom"), _node("Valid")])

    with (
        patch.object(sv, "async_playwright", return_value=_playwright_manager()),
        patch.object(sv, "search_on_google", new=AsyncMock(return_value=urls)),
        patch.object(sv, "run_search_quality_evaluation_standalone", new=evaluate),
        patch.object(sv, "logger") as logger,
    ):
        await sv.main("playwright")

    assert evaluate.await_count == 2
    logger.exception.assert_called_once()
