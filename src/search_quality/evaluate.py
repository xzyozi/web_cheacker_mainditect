"""検索結果ページの品質評価（SQS）のエントリポイント。

監視本流（`web-cheackerV3.py`）からは呼ばれない任意機能。単体実行と `search_and_validate.py` から使う。
重い追加依存（`scikit-learn`、`sentence-transformers`）が必要: `uv sync --extra quality`
"""

import asyncio
import sys

import numpy as np
from playwright.async_api import Browser, async_playwright

from content_extractor import DOMTreeSt, extract_main_content
from content_extractor.playwright_helpers import close_page, setup_page
from utils.setup_logger import setup_logger

from .quality_evaluator import is_no_results_page, quantify_search_results

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = setup_logger("search_quality")


async def evaluate_search_quality(url: str, browser: Browser, search_query: str) -> DOMTreeSt | None:
    """
    検索結果ページの品質を多角的に評価します。
    コンテンツ抽出後、フェーズ1〜3の評価処理を実行します。

    Args:
        url (str): 評価対象のURL。
        browser (Browser): 使用するPlaywrightのBrowserインスタンス。
        search_query (str): 関連性スコア計算のための検索クエリ。

    Returns:
        DOMTreeSt | None: 品質評価情報が付与されたDOMTreeStオブジェクト。
    """
    # 1. まずは純粋なコンテンツ抽出を行う
    content_node = await extract_main_content(url, browser)

    if not content_node:
        return None

    page = await setup_page(url, browser)
    if not page:
        return content_node  # ページ準備に失敗しても、抽出済みのコンテンツは返す

    try:
        # フェーズ1: 「結果なし」ページの高速トリアージ
        if await is_no_results_page(page, content_node):
            logger.info(f"URL: {url} は「結果なし」ページと判定されました。")
            content_node.is_empty_result = True
            return content_node

        # フェーズ2: 検索結果アイテムの定量化
        quantify_search_results(content_node)

        # 定量化の結果、有効なアイテムが0件だった場合も「結果なし」と見なす
        if content_node.result_count == 0:
            logger.info(f"URL: {url} は有効な検索結果アイテムを含まないと判定されました。")
            content_node.is_empty_result = True
            return content_node

        # フェーズ3: 結果の関連性スコアリング
        from .relevance_scorer import RelevanceScorer

        logger.info(f"検索クエリ '{search_query}' との関連性スコアリングを開始します。")
        scorer = RelevanceScorer()
        scored_items = scorer.score_relevance(search_query, content_node.result_items)
        content_node.result_items = scored_items

        if scored_items:
            scores = [item.relevance_score for item in scored_items]
            content_node.avg_relevance = float(np.mean(scores))
            content_node.relevance_variance = float(np.var(scores))
            content_node.max_relevance = float(np.max(scores))
            logger.info(
                f"関連性スコアを計算しました: Avg={content_node.avg_relevance:.2f}, "
                f"Var={content_node.relevance_variance:.2f}, Max={content_node.max_relevance:.2f}"
            )

            # フェーズ4: SQS計算と最終判定
            sqs, category = scorer.calculate_sqs(
                result_count=content_node.result_count,
                avg_relevance=content_node.avg_relevance,
                relevance_variance=content_node.relevance_variance,
                max_relevance=content_node.max_relevance,
            )
            content_node.sqs_score = sqs
            content_node.quality_category = category

        return content_node
    finally:
        await close_page(page)


async def run_search_quality_evaluation_standalone(url: str, search_query: str):
    """
    単一URLの検索品質評価をスタンドアロンで実行します。
    ブラウザの起動と終了を内包します。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            return await evaluate_search_quality(url, browser, search_query)
        finally:
            if browser:
                await browser.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="検索結果ページの品質評価（SQS）を単一URLに対して実行する。")
    parser.add_argument("url", help="評価対象のURL")
    parser.add_argument("--query", "-q", required=True, help="関連性スコア計算に使う検索クエリ")
    args = parser.parse_args()

    result_obj = asyncio.run(run_search_quality_evaluation_standalone(url=args.url, search_query=args.query))
    if result_obj is None:
        logger.warning("コンテンツは抽出されませんでした。")
    elif result_obj.is_empty_result:
        logger.info("品質評価結果: 結果なしページ")
    else:
        logger.info(
            f"品質評価結果: {result_obj.result_count}件 "
            f"(AvgRelevance: {result_obj.avg_relevance:.2f}, SQS: {result_obj.sqs_score:.2f}, "
            f"{result_obj.quality_category})"
        )
