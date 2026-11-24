"""search_quality.evaluate（品質評価のエントリポイント）のテスト。

ブラウザ・関連性スコア（埋め込みモデル）はモック化し、段階ごとの分岐だけを検証する。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from content_extractor.dom_treeSt import DOMTreeSt
from search_quality import evaluate as evaluate_module
from search_quality.evaluate import evaluate_search_quality, run_search_quality_evaluation_standalone

URL = "https://example.com/search?q=python"
QUERY = "python"


def _scored_item(score: float) -> DOMTreeSt:
    item = DOMTreeSt(text="item")
    item.relevance_score = score
    return item


@pytest.fixture
def patched():
    """外部依存（抽出・ページ準備・各評価段階）を差し替える。"""
    page = MagicMock(name="page")
    node = DOMTreeSt(text="main content")
    with (
        patch.object(evaluate_module, "extract_main_content", new=AsyncMock(return_value=node)) as extract,
        patch.object(evaluate_module, "setup_page", new=AsyncMock(return_value=page)) as setup,
        patch.object(evaluate_module, "close_page", new=AsyncMock()) as close,
        patch.object(evaluate_module, "is_no_results_page", new=AsyncMock(return_value=False)) as no_results,
        patch.object(evaluate_module, "quantify_search_results") as quantify,
    ):
        yield MagicMock(
            node=node, page=page, extract=extract, setup=setup, close=close, no_results=no_results, quantify=quantify
        )


@pytest.mark.asyncio
async def test_returns_none_when_extraction_fails(patched):
    """抽出に失敗した場合は None を返し、ページ準備へ進まない。"""
    patched.extract.return_value = None

    assert await evaluate_search_quality(URL, MagicMock(), QUERY) is None
    patched.setup.assert_not_called()


@pytest.mark.asyncio
async def test_returns_extracted_node_when_page_setup_fails(patched):
    """ページ準備に失敗しても、抽出済みのコンテンツは返す（品質評価は付与されない）。"""
    patched.setup.return_value = None

    result = await evaluate_search_quality(URL, MagicMock(), QUERY)

    assert result is patched.node
    assert result.is_empty_result is False
    patched.no_results.assert_not_called()
    patched.close.assert_not_called()


@pytest.mark.asyncio
async def test_no_results_page_is_marked_empty_and_page_is_closed(patched):
    """TR-021: 「結果なし」と判定されたら is_empty_result が真になり、ページは閉じられる。"""
    patched.no_results.return_value = True

    result = await evaluate_search_quality(URL, MagicMock(), QUERY)

    assert result.is_empty_result is True
    patched.quantify.assert_not_called()
    patched.close.assert_awaited_once_with(patched.page)


@pytest.mark.asyncio
async def test_zero_valid_items_is_treated_as_empty(patched):
    """定量化の結果が0件なら「結果なし」とみなし、関連性スコアリングを行わない。"""
    patched.quantify.side_effect = lambda node: setattr(node, "result_count", 0)

    with patch("search_quality.relevance_scorer.RelevanceScorer") as scorer_cls:
        result = await evaluate_search_quality(URL, MagicMock(), QUERY)

    assert result.is_empty_result is True
    scorer_cls.assert_not_called()
    patched.close.assert_awaited_once_with(patched.page)


@pytest.mark.asyncio
async def test_full_flow_sets_relevance_statistics_and_sqs(patched):
    """TR-022: 関連性の平均・分散・最大と、SQS・品質カテゴリが結果へ設定される。"""

    def quantify(node):
        node.result_count = 2
        node.result_items = [_scored_item(0.0), _scored_item(0.0)]

    patched.quantify.side_effect = quantify
    scorer = MagicMock()
    scorer.score_relevance.return_value = [_scored_item(0.2), _scored_item(0.6)]
    scorer.calculate_sqs.return_value = (72.5, "Valid")

    with patch("search_quality.relevance_scorer.RelevanceScorer", return_value=scorer):
        result = await evaluate_search_quality(URL, MagicMock(), QUERY)

    assert result.is_empty_result is False
    assert result.avg_relevance == pytest.approx(0.4)
    assert result.relevance_variance == pytest.approx(0.04)
    assert result.max_relevance == pytest.approx(0.6)
    assert result.sqs_score == 72.5
    assert result.quality_category == "Valid"
    scorer.calculate_sqs.assert_called_once()
    assert scorer.calculate_sqs.call_args.kwargs["result_count"] == 2
    patched.close.assert_awaited_once_with(patched.page)


@pytest.mark.asyncio
async def test_empty_scored_items_leaves_sqs_unset(patched):
    """スコア付きアイテムが空なら、SQSは計算されない。"""

    def quantify(node):
        node.result_count = 1
        node.result_items = [_scored_item(0.0)]

    patched.quantify.side_effect = quantify
    scorer = MagicMock()
    scorer.score_relevance.return_value = []

    with patch("search_quality.relevance_scorer.RelevanceScorer", return_value=scorer):
        result = await evaluate_search_quality(URL, MagicMock(), QUERY)

    scorer.calculate_sqs.assert_not_called()
    assert result.quality_category == ""
    assert result.sqs_score == 0.0


@pytest.mark.asyncio
async def test_page_is_closed_even_when_scoring_raises(patched):
    """関連性スコアリングで例外が出ても、ページは必ず閉じる。"""

    def quantify(node):
        node.result_count = 1
        node.result_items = [_scored_item(0.0)]

    patched.quantify.side_effect = quantify
    scorer = MagicMock()
    scorer.score_relevance.side_effect = RuntimeError("model failure")

    with patch("search_quality.relevance_scorer.RelevanceScorer", return_value=scorer):
        with pytest.raises(RuntimeError, match="model failure"):
            await evaluate_search_quality(URL, MagicMock(), QUERY)

    patched.close.assert_awaited_once_with(patched.page)


@pytest.mark.asyncio
async def test_standalone_launches_evaluates_and_closes_browser():
    """スタンドアロン実行は、ブラウザを起動して評価し、終了時に必ず閉じる。"""
    browser = MagicMock()
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)
    expected = DOMTreeSt(text="evaluated")

    with (
        patch.object(evaluate_module, "async_playwright", return_value=manager),
        patch.object(evaluate_module, "evaluate_search_quality", new=AsyncMock(return_value=expected)) as evaluate,
    ):
        result = await run_search_quality_evaluation_standalone(URL, QUERY)

    assert result is expected
    evaluate.assert_awaited_once_with(URL, browser, QUERY)
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_standalone_closes_browser_when_evaluation_raises():
    """評価が例外で終わっても、ブラウザは閉じられる。"""
    browser = MagicMock()
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=playwright)
    manager.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(evaluate_module, "async_playwright", return_value=manager),
        patch.object(evaluate_module, "evaluate_search_quality", new=AsyncMock(side_effect=ValueError("boom"))),
    ):
        with pytest.raises(ValueError, match="boom"):
            await run_search_quality_evaluation_standalone(URL, QUERY)

    browser.close.assert_awaited_once()
