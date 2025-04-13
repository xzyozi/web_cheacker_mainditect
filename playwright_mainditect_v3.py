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
import util_str
from make_tree import make_tree
from scorer import MainContentScorer
from web_type_chk import WebTypeCHK, WebType
from dom_treeSt import DOMTreeSt, BoundingBox
from setup_logger import setup_logger

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# logger setting 
LOGGER_DATEFORMAT = "%Y%m%d_%H%M%S"
nowtime = datetime.now()
formatted_now = nowtime.strftime(LOGGER_DATEFORMAT)
logger = setup_logger("web-cheacker",log_file=f"./log/web-chk_{formatted_now}.log")

# + ----------------------------------------------------------------
# + save json file
# + ---------------------------------------------------------------
import json
def save_json(data : dict, 
              url : str, 
              directory="data"):
    """
    辞書型のデータをJSONファイルとして保存する
    
    Args:
        data (dict): 保存するデータ
        url (str): データに対応するURL
        directory (str): JSONファイルを保存するディレクトリのパス
    Retrun: 
        None
    """
    domain = util_str.get_domain(url)
    file_path = os.path.join(directory, f"{domain}.json")
    util_str.util_handle_path(file_path)  # ファイルを作成または取得する
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# + ----------------------------------------------------------------
#  screen shot function
# + ----------------------------------------------------------------

# スクリーンショットを撮り、対象要素に色味をつける
def highlight_main_content(driver, main_content, filename):
    # 全画面スクリーンショット
    driver.save_screenshot(filename)
    
    # スクリーンショットに色味をつける
    img = Image.open(filename)
    draw = ImageDraw.Draw(img)
    rect = main_content["rect"]
    
    # メインコンテンツの位置を調整
    x, y = driver.execute_script("return [window.scrollX, window.scrollY];")
    rect["x"] -= x
    rect["y"] -= y
    
    draw.rectangle(((rect["x"], rect["y"]), (rect["x"] + rect["width"], rect["y"] + rect["height"])), outline=(126, 185, 255), width=5)
    img.save(filename)


async def save_screenshot(url_list: list, 
                          save_dir="temp", 
                          width=500, 
                          height : int | None =None
                          ) -> list:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        filelist = []
        os.makedirs(save_dir, exist_ok=True)  # Ensure the folder is created

        for url in url_list[:]:
            # Validate the URL
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.warning(f"Invalid URL skipped: {url}")
                continue

            domain = parsed_url.netloc.replace(".", "_")  # Generate a safe file name from the domain
            filename = generate_filename(url)
            filepath = os.path.join(save_dir, filename)

            try:
                # Navigate to the page and wait for it to load
                await page.goto(url, wait_until='load', timeout=50000)
                await page.screenshot(path=filepath, full_page=True)

                # Resize the image to the specified width and optional height
                with Image.open(filepath) as img:
                    aspect_ratio = img.height / img.width
                    new_height = height if height else int(width * aspect_ratio)
                    resized_img = img.resize((width, new_height))
                    resized_img.save(filepath)

                filelist.append(filepath)  # Add to the list only if successful
            except Exception as e:
                logger.error(f"Failed to process {url}: {e}")
                url_list.remove(url)  # Remove from the list on failure

        await browser.close()

    return filelist

def generate_filename(url: str) -> str:
    """URL から一意なファイル名を生成"""
    parsed_url = urlparse(url)
    
    # ドメイン部分
    domain = parsed_url.netloc.replace(".", "_")

    # パス部分（最後のスラッシュ以降）
    path = parsed_url.path.rstrip("/")  # 最後の `/` を削除
    if "/" in path:
        last_part = path.rsplit("/", 1)[-1]  # 最後の `/` 以降を取得
    else:
        last_part = "index"  # ルートの場合は `index`

    #hash_part = hashlib.md5(url.encode()).hexdigest()[:8]  # MD5の先頭8文字
    filename = f"{domain}_{last_part}.png"

    return filename

# ----------------------------------------------------------------
# debugger 
# ----------------------------------------------------------------
def print_content(content : Dict) -> None:
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
        else : logger.info("no links found")
        logger.info("----------------------------------------------------------")

# error chackintg 
def print_error_details(e : Exception) -> None :
    logger.error(f"Error type: {type(e).__name__}")
    logger.error(f"Error message: {str(e)}")
    logger.error("Traceback:")
    traceback.print_exc(file=sys.stdout)


def update_nodes_with_children(data: Union[Dict[str, Any], List[Dict[str, Any]], DOMTreeSt]) -> Union[List[Dict[str, Any]], List[DOMTreeSt]]:
    """
    Recursively enrich nodes with their descendant nodes and return the enriched nodes in a list.

    Parameters:
    data (Union[Dict[str, Any], List[Dict[str, Any]]]): The root data structure containing nodes.

    Returns:
    List[Dict[str, Any]]: A list of nodes, each enriched with their descendants.
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
    try:
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        await page.wait_for_selector('body', state='attached', timeout=10000)
        try:
            await page.wait_for_load_state('networkidle', timeout=30000)
        except PlaywrightTimeoutError:
            logger.warning("Network did not become idle within 30 seconds, continuing anyway.")
        return page
    except Exception as e:
        logger.error(f"setting up page: {e}")
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
    """Fetch robots.txt content from the target website"""
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
    """Check if scraping is allowed for the given path based on robots.txt"""
    from urllib.robotparser import RobotFileParser
    from io import StringIO

    robot_parser = RobotFileParser()
    robot_parser.parse(StringIO(robots_txt).readlines())
    
    # Check if we are allowed to scrape the target path
    return robot_parser.can_fetch("*", target_path)

async def initialize_browser_and_page(url : str):
    """ブラウザとページを初期化し、スクレイピングの準備をする"""
    playwright = await async_playwright().start()
    try :
        browser = await playwright.chromium.launch(headless=True)
        page = await setup_page(url, browser)
    except Exception as e :
        playwright.stop()
        logger.error("playwright stop")
        return None, None, None
    return playwright, browser, page



async def test_main(url : str,
                    count : int = 0,
                    arg_webtype : any = None
                    ) -> DOMTreeSt | None:       

    max_loop_count = 10

    # Fetch robots.txt
    robots_txt = await fetch_robots_txt(url)
    
    if robots_txt:
        # Check if scraping is allowed
        parsed_url = urlparse(url)
        target_path = parsed_url.path or "/"
        
        if not is_scraping_allowed(robots_txt, target_path):
            logger.info(f"Scraping is not allowed on this URL: {url}")
            return None


    #browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
    playwright, browser, page = await initialize_browser_and_page(url)

    if not page:
        await browser.close()
        await playwright.stop()  # Playwright自体も終了させる
        return None

    try:

        dimensions = await adjust_page_view(page)

        tree = await make_tree(page)
        if not tree:
            logger.info("Error: Empty tree structure returned")
            return None

        # ----------------------------------------------------------------
        # web type cheak
        # ----------------------------------------------------------------
        webtype = WebTypeCHK(url, tree)
        chktype = webtype.webtype_chk()
        watch_url = webtype.next_url

        if watch_url and count < 3 :
            logger.info(f"URL updated: {url} -> {watch_url}. Restarting process...")
            await browser.close()  # 既存のブラウザを閉じる
            await playwright.stop()
            # 前回時点のwebtypeが存在する場合はそちらを採用する
            if arg_webtype:
                return await test_main(watch_url, count + 1, arg_webtype=arg_webtype)  # 再帰的に処理を実行
            else:
                return await test_main(watch_url, count + 1, arg_webtype=chktype)  # 再帰的に処理を実行


        tree = [tree]  # Convert tree to list[Dict]
        scorer = MainContentScorer(tree, dimensions['width'], dimensions['height'])
        main_contents = scorer.find_candidates()

        if not main_contents:
            logger.info("No main content detected.")
            return {}

        logger.info(f"Top candidates:{len(main_contents)}")
        for content in main_contents[:0]:
            logger.info(content)

        if main_contents:
            main_contents = rescore_main_content_with_children(main_contents[0])

            logger.info("main content:")
            logger.info(main_contents[0])
            logger.info(main_contents[1])

            # logger.info("pre content diff:")
            # for content in main_contents[:2]:
            #     print_content(content)

            loop_count = 0
            # tmp_main_content = DOMTreeSt()
            while main_contents:
                tmp_main_content = main_contents[0] 

                main_contents = rescore_main_content_with_children(tmp_main_content)

                logger.info(f" tmp_main selector : {tmp_main_content.css_selector} main selector: {main_contents[0].css_selector}")
                logger.info(f'tmp_candidates score : {tmp_main_content.score}  & main_contents {main_contents[0].score}')
                if tmp_main_content.score >= main_contents[0].score:
                    break

                loop_count += 1
                if loop_count == max_loop_count:
                    logger.warning("loop count MAX")
                    break

            logger.info("Rescored child nodes:")
            for child in main_contents[:5]:
                logger.debug(child)

            logger.info("Selected main content:")
            # print_content(tmp_main_content)
            logger.info(tmp_main_content)

            tmp_main_content.url = url

            # 再帰処理後であれば前回時点
            if arg_webtype :
                tmp_main_content.web_type = arg_webtype
            else : 
                tmp_main_content.web_type = chktype

            json_data = tmp_main_content.to_dict()

            save_json(json_data,url)

            return tmp_main_content
        else:
            logger.warning("No main content detected after initial search.")

            return None

    except Exception as e:
        logger.error("An error occurred during test_main:")
        print_error_details(e)

    finally:
        await browser.close()
        await playwright.stop()  # Playwright自体も終了させる



async def choice_content(url: str, 
                         selector: str,
                         webtype_str : str,
                         ):
    
    webtype = WebType.from_string(webtype_str)
    # logger.info(f"chk webtype : {webtype}({type(webtype)}) -- {WebType.page_changer} ({type(WebType.page_changer)})")
    if webtype == WebType.page_changer :
        logger.warning(f"webtype is pagechange full scan process start :{WebType.page_changer}")
        return await test_main(url,webtype)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        try:
            # ページ移動と初期待機を簡略化
            await page.goto(url, wait_until='load', timeout=10000)
            await page.wait_for_selector(selector, state='attached', timeout=10000)
            
            # コンテンツ読み込みを最適化
            previous_height = None
            while True:
                current_height = await page.evaluate("document.body.scrollHeight")
                if previous_height == current_height:
                    break
                previous_height = current_height
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)  # 必要最小限の待機

            # DOMツリーを取得
            tree = await make_tree(page, selector=selector)
            if not tree:
                logger.info(f"No matching elements found for selector: {selector}")
                return {}
            
            tree.url = url

            return tree

        except Exception as e:
            logger.error(f"Error during content extraction: {str(e)}")
            return None

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    # 使用例
    url = "https://loopholes.site/"
    #url = " https://mangakoma01.net/manga/zhou-shu-hui-zhana004"
    # url = "http://animesoku.com/archives/38156477.html" # ng
    #url = "https://monoschinos2.com/anime/bleach-sennen-kessen-hen-soukoku-tan-sub-espanol"
    url = "https://gamewith.jp/apexlegends/"
    url = "https://s1s1s1.com/top "
    url = "https://f95zone.to/threads/translation-request-big-breasts-party-ntr.52990/page-497"

    import datetime
    sta_sec = datetime.datetime.now()
    dict_obj = asyncio.run(test_main(url))
    end_sec = datetime.datetime.now()

    logger.info(f"full proc {end_sec - sta_sec} seconds")
    logger.info(type(dict_obj))
 
    # choice_dict = {
    #     "id": "ld_blog_article_comment_entries",
    #     "tag": "ol",
    #     "attributes": {"id": "ld_blog_article_comment_entries"}
    # }
    # sta_sec = datetime.datetime.now()

    # end_sec = datetime.datetime.now()
    # ch_tree=  asyncio.run(choice_content(url,"div#article-body[id='article-body']"))
    # logger.info(ch_tree,type(ch_tree))
    # if ch_tree is not None :
    #     content_hash_text = hashlib.sha256(str(ch_tree["links"]).encode()).hexdigest()
    
    #     logger.info(content_hash_text)
    #     end_sec = datetime.datetime.now()
    #     logger.info(f"select scan proc {end_sec - sta_sec} seconds")


    logger.info(datetime.datetime.now())

    # import requests

    # response = requests.get(url)
    # last_modified = response.headers.get("Last-Modified")
    # logger.info(last_modified)