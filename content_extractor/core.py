from typing import Dict, List, Any, Union , Optional

import os
from collections import Counter
import asyncio
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
from aiohttp import ClientError

import traceback
import sys
import hashlib
from datetime import datetime
import numpy as np

# my module 
from .scorer import MainContentScorer
from .make_tree import make_tree
from .web_type_chk import WebTypeCHK, WebType
from .dom_treeSt import DOMTreeSt, BoundingBox
from .dom_utils import rescore_main_content_with_children
from .playwright_helpers import setup_page, adjust_page_view, fetch_robots_txt, is_scraping_allowed
from .quality_evaluator import is_no_results_page, quantify_search_results
from setup_logger import setup_logger
from utils.file_handler import save_json

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# logger setting 
LOGGER_DATEFORMAT = "%Y%m%d_%H%M%S"
nowtime = datetime.now()
formatted_now = nowtime.strftime(LOGGER_DATEFORMAT)
logger = setup_logger("web-cheacker",log_file=f"./log/web-chk_{formatted_now}.log")


# ----------------------------------------------------------------
# debugger 
# ----------------------------------------------------------------
# error chackintg 
def print_error_details(e : Exception) -> None :
    """例外オブジェクトから詳細なエラー情報をログに出力します。"""
    logger.error(f"Error type: {type(e).__name__}")
    logger.error(f"Error message: {str(e)}")
    logger.error("Traceback:")
    traceback.print_exc(file=sys.stdout)


async def extract_main_content(url: str,
                    browser: Browser,
                    count : int = 0,
                    arg_webtype : Any = None
                    ) -> DOMTreeSt | None:       
    """
    URLからメインコンテンツを抽出し、DOMTreeStオブジェクトとして返します。(Fullスキャン)
    robots.txtの確認、ページ遷移の検知、コンテンツのスコアリングと再評価を行います。

    Args:
        url (str): 解析対象のURL。
        browser (Browser): 使用するPlaywrightのBrowserインスタンス。
        count (int, optional): ページ遷移の再帰呼び出し回数カウンタ。デフォルトは 0。
        arg_webtype (Any, optional): 前の処理から引き継がれたWebページタイプ。デフォルトは None。

    Returns:
        DOMTreeSt | None: 抽出されたメインコンテンツのDOMTreeStオブジェクト。失敗した場合はNone。
    """
    page = None
    try:
        # robots.txtを取得
        robots_txt = await fetch_robots_txt(url)
        
        if robots_txt:
            # スクレイピングが許可されているか確認
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            target_path = parsed_url.path or "/"
            
            if not is_scraping_allowed(robots_txt, target_path):
                logger.info(f"robots.txtにより、このURLのスクレイピングは許可されていません: {url}")
                return None

        page = await setup_page(url, browser)
        if not page:
            return None

        max_loop_count = 5
        dimensions = await adjust_page_view(page)

        tree = await make_tree(page)
        if not tree:
            logger.info("Error: Empty tree structure returned")
            return None

        # ----------------------------------------------------------------
        # Webページタイプのチェック
        # ----------------------------------------------------------------
        webtype = WebTypeCHK(url, tree)
        chktype = webtype.webtype_chk()
        watch_url = webtype.next_url

        if watch_url and count < 3 :
            logger.info(f"URL updated: {url} -> {watch_url}. Restarting process...")
            # 前回時点のwebtypeが存在する場合はそちらを採用する
            if arg_webtype:
                return await extract_main_content(watch_url, browser, count + 1, arg_webtype=arg_webtype)  # 再帰的に処理を実行
            else:
                return await extract_main_content(watch_url, browser, count + 1, arg_webtype=chktype)  # 再帰的に処理を実行


        tree = [tree]  # Convert tree to list[Dict]
        scorer = MainContentScorer(tree, dimensions['width'], dimensions['height'])
        main_contents = scorer.find_candidates()

        if not main_contents:
            logger.info("メインコンテンツ候補が見つかりませんでした。")
            return None

        logger.info(f"Top candidates:{len(main_contents)}")

        if main_contents:
            main_contents = rescore_main_content_with_children(main_contents[0])
            
            # logger.info("再評価前のコンテンツ差分:")
            # for content in main_contents[:2]:
            #     print_content(content)

            # =================================================================
            # メインコンテンツ候補の再評価ループ
            # =================================================================
            # 初期候補(mainタグなど)は大きすぎることがある。そのため、その子要素を再評価し、
            # よりスコアの高い(＝よりコンテンツ本体に近い)要素へと絞り込んでいく。
            # 画面占有率などがスコアに大きく影響するため、この絞り込みが重要となる。
            loop_count = 0
            while main_contents:
                # 現在の最有力候補を一時保存
                tmp_main_content = main_contents[0]

                # 最有力候補の子要素を再スコアリングし、新たな候補リストとする
                main_contents = rescore_main_content_with_children(tmp_main_content)

                logger.debug(f" Parent selector : {tmp_main_content.css_selector} / Score: {tmp_main_content.score}")
                if main_contents:
                    logger.debug(f" -> Best Child selector: {main_contents[0].css_selector} / Score: {main_contents[0].score}")

                # 子要素が見つからない、または子要素のスコアが親を超えなくなったら、
                # 親が最良のコンテンツブロックと判断してループを抜ける。
                if not main_contents or tmp_main_content.score >= main_contents[0].score:
                    break

                loop_count += 1
                if loop_count == max_loop_count:
                    logger.warning("再評価ループが上限に達しました。")
                    break
            # while loop end

            logger.info("Rescored child nodes:")
            for child in main_contents[:5]:
                logger.debug(child)

            logger.info("最終的に選択されたメインコンテンツ:")
            logger.info(tmp_main_content)

            # 最終的に選択されたコンテンツを final_content とする
            # この時点では品質評価は行わない
            final_content = tmp_main_content

            # css_selector_list setting
            # 堅牢なセレクタ候補を上位3つまで取得（空のセレクタは除外）
            selector_candidates = [node.css_selector for node in main_contents[:3] if node.css_selector]
            
            # 自身のセレクタも候補の先頭に追加しておく
            if tmp_main_content.css_selector and tmp_main_content.css_selector not in selector_candidates:
                selector_candidates.insert(0, tmp_main_content.css_selector)

            # 最終的に選ばれたコンテンツに、セレクタ候補リストとプライマリセレクタを格納
            final_content.css_selector_list = selector_candidates
            if selector_candidates:
                final_content.css_selector = selector_candidates[0]
            # css_selector_list setting end

            final_content.url = url

            # web_type setting
            current_type = WebType.from_string(chktype)
            if arg_webtype:
                previous_type = WebType.from_string(arg_webtype)
                if current_type.priority > previous_type.priority:
                    final_content.web_type = current_type.name
                else:
                    final_content.web_type = previous_type.name
            else:
                final_content.web_type = current_type.name
            final_content.is_empty_result = False # 明示的にFalseを設定

            json_data = final_content.to_dict()

            # JSONを保存
            save_json(json_data,url)

            return final_content
        else:
            logger.warning("最初の探索でメインコンテンツが見つかりませんでした。")

            return None

    except PlaywrightTimeoutError as e:
        logger.error(f"Playwrightの操作中にタイムアウトが発生しました: {url} - {e}")
        print_error_details(e)
        return None
    except ClientError as e:
        logger.error(f"HTTPリクエスト中にエラーが発生しました: {url} - {e}")
        print_error_details(e)
        return None
    except Exception as e:
        logger.error(f"extract_main_contentの実行中に予期せぬエラーが発生しました: {url}")
        print_error_details(e)
        return None

    finally:
        if page:
            await page.close()


async def evaluate_search_quality(url: str,
                                  browser: Browser,
                                  search_query: str
                                  ) -> DOMTreeSt | None:
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
        return content_node # ページ準備に失敗しても、抽出済みのコンテンツは返す

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
            content_node.avg_relevance = np.mean(scores)
            content_node.relevance_variance = np.var(scores)
            content_node.max_relevance = np.max(scores)
            logger.info(f"関連性スコアを計算しました: Avg={content_node.avg_relevance:.2f}, Var={content_node.relevance_variance:.2f}, Max={content_node.max_relevance:.2f}")

            # フェーズ4: SQS計算と最終判定
            sqs, category = scorer.calculate_sqs(
                result_count=content_node.result_count,
                avg_relevance=content_node.avg_relevance,
                relevance_variance=content_node.relevance_variance,
                max_relevance=content_node.max_relevance
            )
            content_node.sqs_score = sqs
            content_node.quality_category = category

        return content_node
    finally:
        await page.close()

async def quick_extract_content(url: str,
                                browser: Browser,
                                css_selector_list: list[str],
                                webtype_str: str,
                                ):
    """
    CSSセレクタリストを使用して、ページから迅速にメインコンテンツを抽出します。(Quickスキャン)
    セレクタが見つかった場合、その要素をDOMツリーとして返します。

    Args:
        url (str): 解析対象のURL。
        browser (Browser): 使用するPlaywrightのBrowserインスタンス。
        css_selector_list (list[str]): 試行するCSSセレクタのリスト。
        webtype_str (str): Webページのタイプを示す文字列。

    Returns:
        DOMTreeSt | None: 抽出されたメインコンテンツのDOMTreeStオブジェクト。失敗した場合はNone。
    """
    
    webtype = WebType.from_string(webtype_str)
    # logger.info(f"chk webtype : {webtype}({type(webtype)}) -- {WebType.page_changer} ({type(WebType.page_changer)})")
    if webtype == WebType.page_changer or webtype == WebType.not_quickscan :
        logger.warning(f"webtype is pagechange full scan process start :{webtype}")
        return await extract_main_content(url, browser, arg_webtype=webtype)

    if webtype in [WebType.page_changer, WebType.not_quickscan]:
        logger.warning(f"webtype is pagechange, starting full scan process: {webtype}")
        return await extract_main_content(url, browser, arg_webtype=webtype)

    # セレクタリストが空の場合はFullスキャンに移行
    if not css_selector_list:
        logger.warning("No selectors provided for quick scan, starting full scan.")
        return await extract_main_content(url, browser, arg_webtype=webtype)

    context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = await context.new_page()
    
    try:
        found_tree = None
        # ページ移動と初期待機を簡略化
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)

        # セレクタをループで試す
        for selector in css_selector_list:
            try:
                # 短いタイムアウトでセレクタの存在を確認
                await page.wait_for_selector(selector, state='attached', timeout=5000)
                logger.info(f"Selector found, extracting content with: {selector}")
                tree = await make_tree(page, selector=selector)
                if tree:
                    found_tree = tree
                    # Quickスキャン成功時は、成功したセレクタをプライマリとし、リストの先頭に持ってくる
                    css_selector_list.remove(selector)
                    css_selector_list.insert(0, selector)
                    found_tree.css_selector_list = css_selector_list
                    found_tree.css_selector = selector
                    break # 見つかったらループを抜ける
            except PlaywrightTimeoutError:
                logger.debug(f"Selector failed, trying next: {selector}")
                continue # 次のセレクタへ
        
        if not found_tree:
            logger.warning(f"All selectors failed for URL: {url}. Quick scan failed.")
            return None # 全て失敗したらNoneを返す

        found_tree.url = url
        found_tree.web_type = webtype_str
        return found_tree

    except PlaywrightTimeoutError as e:
        logger.error(f"Quickスキャン中のPlaywright操作でタイムアウトしました: {url} - {e}")
        return None # Quickスキャン失敗
    except Exception as e:
        logger.error(f"Quickスキャン中に予期せぬエラーが発生: {url}")
        print_error_details(e)
        return None # Quickスキャン失敗
    finally:
        await context.close()


async def run_full_scan_standalone(url: str, arg_webtype: Any = None):
    """
    従来のtest_mainと同様に、単一URLのフルスキャンをスタンドアロンで実行します。
    ブラウザの起動と終了を内包します。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            return await extract_main_content(url, browser, arg_webtype=arg_webtype)
        finally:
            if browser:
                await browser.close()


async def run_quick_scan_standalone(url: str, css_selector_list: list[str], webtype_str: str):
    """
    従来のchoice_contentと同様に、単一URLのクイックスキャンをスタンドアロンで実行します。
    ブラウザの起動と終了を内包します。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            return await quick_extract_content(url, browser, css_selector_list, webtype_str)
        finally:
            if browser:
                await browser.close()


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
    import time

    # --- コマンドライン引数の設定 ---
    parser = argparse.ArgumentParser(
        description="""
        Playwright Main Content Detection Script.
        Used for testing the content extraction logic on a single URL.
        """
    )
    parser.add_argument("url", help="The URL to test.")
    parser.add_argument(
        "--mode", "-m",
        choices=["full", "quick", "quality"],
        default="full",
        help="Scan mode to execute. 'full' runs full scan, 'quick' runs quick scan. Default: full"
    )
    parser.add_argument(
        "--selectors",
        nargs='+',
        help="CSS selector(s) to use for 'quick' mode."
    )
    parser.add_argument(
        "--query", "-q",
        help="Search query to use for 'quality' mode."
    )
    args = parser.parse_args()

    # --- 実行ロジック ---
    start_time = time.time()
    logger.info(f"Starting test for URL: {args.url} (Mode: {args.mode})")

    result_obj = None

    if args.mode == 'full':
        # --- Fullスキャン実行 ---
        logger.info("Fullスキャンを実行します...")
        result_obj = asyncio.run(run_full_scan_standalone(args.url))

    elif args.mode == 'quick':
        # --- Quickスキャン実行 ---
        if not args.selectors:
            logger.error("エラー: 'quick'モードには --selectors が必要です。")
            sys.exit(1)
        
        logger.info(f"Quickスキャンを実行します (セレクタ: {args.selectors})")
        result_obj = asyncio.run(run_quick_scan_standalone(url=args.url, css_selector_list=args.selectors, webtype_str="plane"))

    elif args.mode == 'quality':
        # --- 品質評価スキャン実行 ---
        if not args.query:
            logger.error("エラー: 'quality'モードには --query が必要です。")
            sys.exit(1)
        logger.info(f"品質評価スキャンを実行します (クエリ: '{args.query}')")
        result_obj = asyncio.run(run_search_quality_evaluation_standalone(url=args.url, search_query=args.query))

    end_time = time.time()
    processing_time = end_time - start_time

    # --- 実行結果の表示 ---
    if result_obj:
        logger.info("Test finished successfully.")
        logger.info(f"Primary CSS Selector: {result_obj.css_selector}")
        logger.info(f"Selector Candidates: {result_obj.css_selector_list}")
        logger.info(f"Extracted Links Count: {len(result_obj.links)}")
        if result_obj.is_empty_result:
            logger.info("品質評価結果: 結果なしページ")
        elif result_obj.result_count > 0:
            logger.info(f"品質評価結果: {result_obj.result_count}件のアイテムを検出 (AvgRelevance: {result_obj.avg_relevance:.2f})")
        # print(result_obj) # オブジェクト全体を詳細に見たい場合はコメントを外す
    else:
        logger.warning("テストは終了しましたが、コンテンツは抽出されませんでした。")

    logger.info(f"総処理時間: {processing_time:.2f} 秒")
