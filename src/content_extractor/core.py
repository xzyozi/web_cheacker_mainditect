import asyncio
from datetime import datetime
import re
import sys
from typing import Any

from aiohttp import ClientError
from playwright.async_api import Browser, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utils.file_handler import save_json

# my module
from utils.setup_logger import setup_logger

from .dom_treeSt import DOMTreeSt
from .dom_utils import rescore_main_content_with_children
from .make_tree import make_tree
from .playwright_helpers import (
    adjust_page_view,
    close_page,
    ensure_unique_selector,
    is_url_allowed,
    setup_page,
)
from .scorer import MainContentScorer
from .web_type_chk import WebType, WebTypeCHK


def _escape_css_selector_colons(selector: str) -> str:
    """
    CSSセレクタ内のクラス名に含まれるコロンをエスケープします。
    TailwindCSSなどで生成されるクラス名（例: 'md:px-4'）が
    Playwrightのwait_for_selectorで正しく解釈されるようにします。
    """
    # 正規表現を使って、ドットの後に続くコロンをエスケープ
    # 例: .md:px-12 -> .md\:px-12
    # ただし、すでにエスケープされている場合は無視する
    escaped_selector = re.sub(r"(?<!\\)([.][a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)", r"\1\\:\2", selector)
    return escaped_selector


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# logger setting
LOGGER_DATEFORMAT = "%Y%m%d_%H%M%S"
nowtime = datetime.now()
formatted_now = nowtime.strftime(LOGGER_DATEFORMAT)
logger = setup_logger("web-cheacker", log_file=f"./log/web-chk_{formatted_now}.log")


# ----------------------------------------------------------------
# debugger
# ----------------------------------------------------------------


async def extract_main_content(url: str, browser: Browser, count: int = 0, arg_webtype: Any = None) -> DOMTreeSt | None:
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
        if not await is_url_allowed(url):
            logger.info(f"robots.txtにより、このURLのスクレイピングは許可されていません: {url}")
            return None

        page = await setup_page(url, browser)
        if not page:
            return None

        max_loop_count = 5
        dimensions = await adjust_page_view(page)

        # setup_page と adjust_page_view で既に待機済みのため、重複の networkidle 待機は行わない
        tree = await make_tree(page, wait_for_load=False)
        if not tree:
            logger.info("Error: Empty tree structure returned")
            return None

        # ----------------------------------------------------------------
        # Webページタイプのチェック
        # ----------------------------------------------------------------
        webtype = WebTypeCHK(url, tree)
        chktype = webtype.webtype_chk()
        watch_url = webtype.next_url

        if watch_url and count < 3:
            logger.info(f"URL updated: {url} -> {watch_url}. Restarting process...")
            # 再帰呼び出し前に現在のページを解放し、finally での二重クローズを防ぐ
            current_page = page
            page = None
            await close_page(current_page)
            # 前回時点のwebtypeが存在する場合はそちらを採用する
            next_webtype = arg_webtype if arg_webtype else chktype
            return await extract_main_content(
                watch_url, browser, count + 1, arg_webtype=next_webtype
            )  # 再帰的に処理を実行

        scorer = MainContentScorer([tree], dimensions["width"], dimensions["height"])
        main_contents = scorer.find_candidates()

        if not main_contents:
            logger.info("メインコンテンツ候補が見つかりませんでした。")
            return None

        logger.info(f"Top candidates:{len(main_contents)}")

        if main_contents:
            # =================================================================
            # メインコンテンツ候補の再評価ループ
            # =================================================================
            # 初期候補(mainタグなど)は大きすぎることがある。そのため、その子要素を再評価し、
            # よりスコアの高い(＝よりコンテンツ本体に近い)要素へと絞り込んでいく。
            # 画面占有率などがスコアに大きく影響するため、この絞り込みが重要となる。
            # =================================================================
            loop_count = 0
            current_best = main_contents[0]
            # このリストは、前回のイテレーションで評価された`current_best`の子要素を保持します。
            # これは`selector_candidates`を生成するために使用されます。
            current_best_children = []

            while loop_count < max_loop_count:
                # 現在の最有力候補を一時保存 (次のイテレーションでprev_bestとなる)
                prev_best = current_best

                # 最有力候補の子要素を再スコアリングし、新たな候補リストとする
                rescored_children_of_prev_best = rescore_main_content_with_children(prev_best)

                logger.debug(f" Parent selector : {prev_best.css_selector} / Score: {prev_best.score}")
                if rescored_children_of_prev_best:
                    logger.debug(
                        f" -> Best Child selector: {rescored_children_of_prev_best[0].css_selector}"
                        f" / Score: {rescored_children_of_prev_best[0].score}"
                    )

                # 子要素が見つからない、または子要素のスコアが親を超えなくなったら、
                # 親が最良のコンテンツブロックと判断してループを抜ける。
                if not rescored_children_of_prev_best or prev_best.score >= rescored_children_of_prev_best[0].score:
                    current_best_children = rescored_children_of_prev_best  # Keep these for selector generation
                    break

                # もしより良い子要素が見つかったら、それを新たなcurrent_bestとし、その子リストを保持する
                current_best = rescored_children_of_prev_best[0]
                current_best_children = rescored_children_of_prev_best  # Update children for the new current_best
                loop_count += 1

            if loop_count == max_loop_count:
                logger.warning("再評価ループが上限に達しました。")
                # 上限到達時は直前のcurrent_best（前ループの子）自身の子孫だけから候補を作る
                current_best_children = rescore_main_content_with_children(current_best)

            final_content = current_best

            logger.info("最終的に選択されたメインコンテンツ:")
            logger.info(final_content)

            # 最終的に選択されたコンテンツの子ノードをログ出力
            logger.info("Rescored child nodes of final content:")
            for child in current_best_children[:5]:  # Display up to 5 children
                logger.debug(child)

            # 保存するプライマリセレクタが、ページ内で複数の要素にヒットすると、次回のQuickスキャンで
            # 別の要素を拾って誤検知する。複数ヒットのときは、位置から一意なパスに置き換える。
            final_content.css_selector = await ensure_unique_selector(
                page, final_content.css_selector, final_content.rect.to_dict()
            )

            # css_selector_list setting
            # 堅牢なセレクタ候補を上位3つまで取得（空のセレクタは除外）
            # `current_best_children`は`final_content`の子要素のリストになっている
            selector_candidates = [node.css_selector for node in current_best_children[1:4] if node.css_selector]

            # 自身のセレクタも候補の先頭に追加しておく
            if final_content.css_selector and final_content.css_selector not in selector_candidates:
                selector_candidates.insert(0, final_content.css_selector)

            # 最終的に選ばれたコンテンツに、セレクタ候補リストとプライマリセレクタを格納
            # この時点では品質評価は行わない
            final_content.css_selector_list = selector_candidates
            if (
                selector_candidates and not final_content.css_selector
            ):  # final_content.css_selectorがまだ設定されていない場合にのみ割り当てる
                final_content.css_selector = selector_candidates[0]
            # css_selector_list 設定終了

            final_content.url = url

            # web_type 設定
            current_type = WebType.from_string(chktype)
            if arg_webtype:
                previous_type = WebType.from_string(arg_webtype)
                if current_type.priority > previous_type.priority:
                    final_content.web_type = current_type.name
                else:
                    final_content.web_type = previous_type.name
            else:
                final_content.web_type = current_type.name
            final_content.is_empty_result = False  # 明示的にFalseを設定

            json_data = final_content.to_dict()

            # JSONを保存
            save_json(json_data, url)

            return final_content
        else:
            logger.warning("最初の探索でメインコンテンツが見つかりませんでした。")

            return None

    except PlaywrightTimeoutError as e:
        logger.exception(f"Playwrightの操作中にタイムアウトが発生しました: {url} - {e}")
        return None
    except PlaywrightError as e:
        logger.exception(f"Playwrightの操作中にエラーが発生しました: {url} - {e}")
        return None
    except (ClientError, asyncio.TimeoutError) as e:
        logger.exception(f"HTTPリクエスト中にエラーが発生しました: {url} - {e}")
        return None
    except OSError as e:
        logger.exception(f"ファイルI/O中にエラーが発生しました: {url} - {e}")
        return None
    except Exception:
        logger.exception(f"extract_main_contentの実行中に予期せぬエラーが発生しました: {url}")
        raise

    finally:
        if page:
            await close_page(page)


async def quick_extract_content(
    url: str,
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
    if webtype == WebType.page_changer or webtype == WebType.not_quickscan:
        logger.warning(f"webtype is pagechange full scan process start :{webtype}")
        return await extract_main_content(url, browser, arg_webtype=webtype)

    # セレクタリストが空の場合はFullスキャンに移行
    if not css_selector_list:
        logger.warning("No selectors provided for quick scan, starting full scan.")
        return await extract_main_content(url, browser, arg_webtype=webtype)

    # Full スキャンと同様に、robots.txt で許可されていない URL にはアクセスしない
    if not await is_url_allowed(url):
        logger.info(f"robots.txtにより、このURLのQuickスキャンは許可されていません: {url}")
        return None

    context = await browser.new_context(viewport={"width": 1920, "height": 1080})

    try:
        page = await context.new_page()
        found_tree = None
        # ページ移動と初期待機を簡略化
        await page.goto(url, wait_until="domcontentloaded", timeout=10000)

        # セレクタをループで試す
        for selector in css_selector_list:
            escaped_selector = _escape_css_selector_colons(selector)
            try:
                # 短いタイムアウトでセレクタの存在を確認
                await page.wait_for_selector(escaped_selector, state="attached", timeout=5000)
                logger.info(f"Selector found, extracting content with: {escaped_selector}")
                # page.wait_for_selector で要素を確認済みのため networkidle 再待機せず、ルート要素のみ収集する
                tree = await make_tree(page, selector=escaped_selector, wait_for_load=False, include_children=False)
                if tree:
                    found_tree = tree
                    # Quickスキャン成功時は、成功したセレクタをプライマリとし、リストの先頭に持ってくる
                    css_selector_list.remove(selector)
                    css_selector_list.insert(0, selector)
                    found_tree.css_selector_list = css_selector_list
                    found_tree.css_selector = selector
                    break  # 見つかったらループを抜ける
            except (PlaywrightTimeoutError, PlaywrightError):
                # 無効なセレクタは TimeoutError ではなく Error になるため、同様に次のセレクタへ進む
                logger.debug(f"Selector failed, trying next: {escaped_selector}")
                continue  # 次のセレクタへ

        if not found_tree:
            logger.warning(f"All selectors failed for URL: {url}. Quick scan failed.")
            return None  # 全て失敗したらNoneを返す

        found_tree.url = url
        found_tree.web_type = webtype_str
        return found_tree

    except PlaywrightTimeoutError as e:
        logger.error(f"Quickスキャン中のPlaywright操作でタイムアウトしました: {url} - {e}")
        return None  # Quickスキャン失敗
    except PlaywrightError as e:
        logger.exception(f"Quickスキャン中のPlaywright操作でエラーが発生しました: {url} - {e}")
        return None  # Quickスキャン失敗
    except Exception:
        logger.exception(f"Quickスキャン中に予期せぬエラーが発生: {url}")
        raise
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


if __name__ == "__main__":
    import argparse
    import time

    # --- コマンドライン引数の設定 ---
    parser = argparse.ArgumentParser(
        description="""
        Playwrightを用いたメインコンテンツ検出スクリプト。
        単一URLにおけるコンテンツ抽出ロジックのテストに使用されます。
        """
    )
    parser.add_argument("url", help="The URL to test.")
    parser.add_argument(
        "--mode",
        "-m",
        choices=["full", "quick"],
        default="full",
        help="実行するスキャンモード。'full'はフルスキャン、'quick'はクイックスキャンを実行します。デフォルト: full",
    )
    parser.add_argument("--selectors", nargs="+", help="'quick'モードで使用するCSSセレクタ。")
    args = parser.parse_args()

    # --- 実行ロジック ---
    start_time = time.time()
    logger.info(f"Starting test for URL: {args.url} (Mode: {args.mode})")

    result_obj = None

    if args.mode == "full":
        # --- Fullスキャン実行 ---
        logger.info("Fullスキャンを実行します...")
        result_obj = asyncio.run(run_full_scan_standalone(args.url))

    elif args.mode == "quick":
        # --- Quickスキャン実行 ---
        if not args.selectors:
            logger.error("エラー: 'quick'モードには --selectors が必要です。")
            sys.exit(1)

        logger.info(f"Quickスキャンを実行します (セレクタ: {args.selectors})")
        result_obj = asyncio.run(
            run_quick_scan_standalone(url=args.url, css_selector_list=args.selectors, webtype_str="plane")
        )

    end_time = time.time()
    processing_time = end_time - start_time

    # --- 実行結果の表示 ---
    if result_obj:
        logger.info("Test finished successfully.")
        logger.info(f"Primary CSS Selector: {result_obj.css_selector}")
        logger.info(f"Selector Candidates: {result_obj.css_selector_list}")
        logger.info(f"Extracted Links Count: {len(result_obj.links)}")
        # print(result_obj) # オブジェクト全体を詳細に見たい場合は、この行のコメントを外してください
    else:
        logger.warning("テストは終了しましたが、コンテンツは抽出されませんでした。")

    logger.info(f"総処理時間: {processing_time:.2f} 秒")
