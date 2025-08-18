from typing import Dict, List, Any, Union , Optional
from concurrent.futures import ThreadPoolExecutor

import os
import asyncio
from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError

import traceback

import numpy as np
from PIL import Image, ImageDraw
from urllib.parse import urlparse, urljoin
import aiohttp
import sys
from urllib.parse import urlparse
import hashlib
from datetime import datetime

# my module 
from .scorer import MainContentScorer
from .make_tree import make_tree
from .web_type_chk import WebTypeCHK, WebType
from .dom_treeSt import DOMTreeSt, BoundingBox
from setup_logger import setup_logger
from utils.file_handler import save_json

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# logger setting 
LOGGER_DATEFORMAT = "%Y%m%d_%H%M%S"
nowtime = datetime.now()
formatted_now = nowtime.strftime(LOGGER_DATEFORMAT)
logger = setup_logger("web-cheacker",log_file=f"./log/web-chk_{formatted_now}.log")

# ----------------------------------------------------------------
# debugger 
# ----------------------------------------------------------------
def print_content(content : Dict) -> None:
    """デバッグ用にコンテンツの詳細情報をログに出力します。"""
    if content['score'] > 0:
        logger.info(f"Tag: {content['tag']}, Score: {content['score']}, id: {content['id']}")
        # logger.info(f"children: {content['children']}")
        logger.info(f"attributes: {content['attributes']}")
        logger.info(f"Rect: {content['rect']}")
        logger.info(f"depth: {content['depth']}")
        logger.info(f"css_selector: {content['css_selector']}")
        # if len(content['children']) < 50 :
        #     logger.info(f"text attributes: {content['text']}")
        if content['links'] :
            logger.info(f"Links: {', '.join(content.get('links', []))}")
        else : logger.info("リンクは見つかりませんでした")
        logger.info("----------------------------------------------------------")

# error chackintg 
def print_error_details(e : Exception) -> None :
    """例外オブジェクトから詳細なエラー情報をログに出力します。"""
    logger.error(f"Error type: {type(e).__name__}")
    logger.error(f"Error message: {str(e)}")
    logger.error("Traceback:")
    traceback.print_exc(file=sys.stdout)


def update_nodes_with_children(data: Union[Dict[str, Any], List[Dict[str, Any]], DOMTreeSt]) -> Union[List[Dict[str, Any]], List[DOMTreeSt]]:
    """
    ノードを再帰的にたどり、すべての子孫ノードを含む平坦なリストを返します。

    Args:
        data (Union[Dict[str, Any], List[Dict[str, Any]], DOMTreeSt]): 処理対象のルートとなるノードデータ。

    Returns:
        Union[List[Dict[str, Any]], List[DOMTreeSt]]: すべてのノードを含むリスト。
    """
    updated_nodes = []

    if isinstance(data, list):
        for node in data:
            updated_nodes.extend(update_nodes_with_children(node))
    elif isinstance(data, dict):
        # all_children = get_all_children(data)
        # data['all_children'] = all_children
        updated_nodes.append(data)
        if 'children' in data:
            updated_nodes.extend(update_nodes_with_children(data['children']))

    elif isinstance(data, DOMTreeSt):
        updated_nodes.append(data)
        if data.children :
            updated_nodes.extend(update_nodes_with_children(data.children))

    else :
        logger.info(f"type error : {type(data)} -> {data}")

    return updated_nodes


def rescore_main_content_with_children(main_content : DOMTreeSt, 
                                       driver=None
                                       ) -> list[DOMTreeSt]:
    """
    メインコンテンツ候補とその子ノードを再評価し、スコアの高い順にソートしたリストを返します。

    Args:
        main_content (DOMTreeSt): 評価対象のメインコンテンツ候補ノード。
        driver: (未使用)

    Returns:
        list[DOMTreeSt]: 再評価され、スコアでソートされたノードのリスト。
    
    Raises:
        TypeError: main_contentがDOMTreeStでない場合に発生します。
    """
    if not isinstance(main_content, DOMTreeSt):
        raise TypeError("main_content must be a DOMTreeSt")

    # メインコンテンツのサイズを取得
    main_rect = main_content.rect
    main_width = main_rect.width
    main_height = main_rect.height


    # 親ノードとその子ノードのlistを作成
    scorer_list = update_nodes_with_children(main_content)

    # 子ノードに対してスコアリングを行う
    scorer = MainContentScorer(scorer_list, main_width, main_height)

    # 親ノードとその子ノードのスコアを比較する
    scored_nodes = scorer.score_parent_and_children()

    # スコアをチェック
    # for node in scored_nodes:
    #     logger.info(f"Tag: {node['tag']}, Score: {node['score']}")

    # スコアの高い順に子ノードを並べ替える
    scored_nodes.sort(key=lambda x: x.score, reverse=True)

    return scored_nodes

async def setup_page(url : str, 
                     browser : Browser
                     ):
    """
    指定されたURLのページを準備し、Pageオブジェクトを返します。
    ページの読み込みとネットワークの安定を待ちます。

    Args:
        url (str): 読み込むページのURL。
        browser (Browser): 使用するPlaywrightのBrowserインスタンス。

    Returns:
        Page | None: 準備が完了したPageオブジェクト。失敗した場合はNone。
    """
    try:
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        await page.wait_for_selector('body', state='attached', timeout=10000)
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning("ネットワークが15秒以内にアイドル状態になりませんでした。処理を続行します。")
        return page
    except Exception as e:
        logger.error(f"ページのセットアップ中にエラーが発生: {e}")
        traceback.print_exc()
        return None

async def adjust_page_view(page: Page) -> dict:
    """ページのサイズを調整し、スクロールを実行"""
    dimensions = await page.evaluate('''() => {
        return {
            width: Math.max(document.body.scrollWidth, document.body.offsetWidth, 
                            document.documentElement.clientWidth, document.documentElement.scrollWidth, 
                            document.documentElement.offsetWidth),
            height: Math.max(document.body.scrollHeight, document.body.offsetHeight, 
                             document.documentElement.clientHeight, document.documentElement.scrollHeight, 
                             document.documentElement.offsetHeight)
        }
    }''')

    await page.set_viewport_size({"width": dimensions['width'], "height": dimensions['height']})
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await page.wait_for_timeout(2000)

    return dimensions


async def fetch_robots_txt(url):
    """
    対象ウェブサイトからrobots.txtの内容を取得します。

    Args:
        url (str): 対象サイトのURL。

    Returns:
        str | None: robots.txtのテキスト内容。取得失敗時はNone。
    """
    parsed_url = urlparse(url)
    robots_url = urljoin(f"{parsed_url.scheme}://{parsed_url.netloc}", '/robots.txt')
    
    async with aiohttp.ClientSession() as session:
        async with session.get(robots_url) as response:
            if response.status == 200:
                return await response.text()
            return None

def is_scraping_allowed(robots_txt : str, 
                        target_path : str,
                        ) -> bool:
    """
    robots.txtの内容に基づき、指定されたパスのスクレイピングが許可されているか確認します。

    Args:
        robots_txt (str): robots.txtのテキスト内容。
        target_path (str): 確認するURLのパス。

    Returns:
        bool: スクレイピングが許可されていればTrue。
    """
    from urllib.robotparser import RobotFileParser
    from io import StringIO

    robot_parser = RobotFileParser()
    robot_parser.parse(StringIO(robots_txt).readlines())
    
    # 指定されたパスのスクレイピングが許可されているか確認
    return robot_parser.can_fetch("*", target_path)




async def extract_main_content(url: str,
                    browser: Browser,
                    count : int = 0,
                    arg_webtype : any = None
                    ) -> DOMTreeSt | None:       
    """
    URLからメインコンテンツを抽出し、DOMTreeStオブジェクトとして返します。(Fullスキャン)
    robots.txtの確認、ページ遷移の検知、コンテンツのスコアリングと再評価を行います。

    Args:
        url (str): 解析対象のURL。
        browser (Browser): 使用するPlaywrightのBrowserインスタンス。
        count (int, optional): ページ遷移の再帰呼び出し回数カウンタ。デフォルトは 0。
        arg_webtype (any, optional): 前の処理から引き継がれたWebページタイプ。デフォルトは None。

    Returns:
        DOMTreeSt | None: 抽出されたメインコンテンツのDOMTreeStオブジェクト。失敗した場合はNone。
    """
    # robots.txtを取得
    robots_txt = await fetch_robots_txt(url)
    
    if robots_txt:
        # スクレイピングが許可されているか確認
        parsed_url = urlparse(url)
        target_path = parsed_url.path or "/"
        
        if not is_scraping_allowed(robots_txt, target_path):
            logger.info(f"robots.txtにより、このURLのスクレイピングは許可されていません: {url}")
            return None


    page = await setup_page(url, browser)
    if not page:
        return None

    try:
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
            return {}

        logger.info(f"Top candidates:{len(main_contents)}")
        for content in main_contents[:0]:
            logger.info(content)

        if main_contents:
            main_contents = rescore_main_content_with_children(main_contents[0])
            
            # logger.info("再評価前のコンテンツ差分:")
            # for content in main_contents[:2]:
            #     print_content(content)

            loop_count = 0
            # tmp_main_content = DOMTreeSt()
            while main_contents:
                tmp_main_content = main_contents[0] 

                main_contents = rescore_main_content_with_children(tmp_main_content)

                logger.debug(f" tmp_main selector : {tmp_main_content.css_selector} main selector: {main_contents[0].css_selector}")
                logger.debug(f'tmp_candidates score : {tmp_main_content.score}  & main_contents {main_contents[0].score}')
                if tmp_main_content.score >= main_contents[0].score:
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
            # print_content(tmp_main_content)
            logger.info(tmp_main_content)

            # css_selector_list setting
            # 堅牢なセレクタ候補を上位3つまで取得（空のセレクタは除外）
            selector_candidates = [node.css_selector for node in main_contents[:3] if node.css_selector]
            
            # 自身のセレクタも候補の先頭に追加しておく
            if tmp_main_content.css_selector and tmp_main_content.css_selector not in selector_candidates:
                selector_candidates.insert(0, tmp_main_content.css_selector)

            # 最終的に選ばれたコンテンツに、セレクタ候補リストとプライマリセレクタを格納
            tmp_main_content.css_selector_list = selector_candidates
            if selector_candidates:
                tmp_main_content.css_selector = selector_candidates[0]
            # css_selector_list setting end

            tmp_main_content.url = url

            # web_type setting 再帰処理後であれば前回時点
            if arg_webtype :
                tmp_main_content.web_type = arg_webtype
            else : 
                tmp_main_content.web_type = chktype

            json_data = tmp_main_content.to_dict()

            # JSONを保存
            save_json(json_data,url)

            return tmp_main_content
        else:
            logger.warning("最初の探索でメインコンテンツが見つかりませんでした。")

            return None

    except Exception as e:
        logger.error("extract_main_contentの実行中にエラーが発生しました:")
        print_error_details(e)

    finally:
        if page:
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
        await page.goto(url, wait_until='load', timeout=10000)

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

    except Exception as e:
        logger.error(f"コンテンツ抽出中にエラーが発生: {str(e)}")
        return None # Quickスキャン失敗
    finally:
        await context.close()


async def run_full_scan_standalone(url: str, arg_webtype: any = None):
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
        "--mode",
        choices=["full", "quick"],
        default="full",
        help="Scan mode to execute. 'full' runs full scan, 'quick' runs quick scan. Default: full"
    )
    parser.add_argument(
        "--selectors",
        nargs='+',
        help="CSS selector(s) to use for 'quick' mode."
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

    end_time = time.time()
    processing_time = end_time - start_time

    # --- 実行結果の表示 ---
    if result_obj:
        logger.info("Test finished successfully.")
        logger.info(f"Primary CSS Selector: {result_obj.css_selector}")
        logger.info(f"Selector Candidates: {result_obj.css_selector_list}")
        logger.info(f"Extracted Links Count: {len(result_obj.links)}")
        # print(result_obj) # オブジェクト全体を詳細に見たい場合はコメントを外す
    else:
        logger.warning("テストは終了しましたが、コンテンツは抽出されませんでした。")

    logger.info(f"総処理時間: {processing_time:.2f} 秒")
