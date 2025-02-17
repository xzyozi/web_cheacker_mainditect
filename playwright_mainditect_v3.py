from typing import Dict, List, Any, Union , Optional
from concurrent.futures import ThreadPoolExecutor

import os
import asyncio
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

import traceback

import numpy as np
from PIL import Image, ImageDraw
from urllib.parse import urlparse, urljoin
import aiohttp
import sys
from urllib.parse import urlparse
import hashlib

# my module 
import util_str
from get_tree import get_tree
from scorer import MainContentScorer

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# + ----------------------------------------------------------------
# + save json file
# + ---------------------------------------------------------------
import json
def save_json(data, file_path="./data/json.json") :
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# async def is_html_element(el) -> bool:
#     try:
#         # Check if the element has a tagName property
#         tag_name = await el.evaluate('el => el.tagName')
#         return True
#     except:
#         return False



# async def is_visible_element(element, page: Page) -> bool:
#     if not element:
#         return False

#     tag_name = await element.evaluate('el => el.tagName.toUpperCase()')
#     if tag_name in ["META", "SCRIPT", "LINK", "STYLE", "IFRAME"]:
#         return False

#     is_visible = await element.is_visible()
#     if not is_visible:
#         return False

#     opacity = await element.evaluate('el => window.getComputedStyle(el).opacity')
#     if float(opacity) == 0:
#         return False

#     z_index = await element.evaluate('el => window.getComputedStyle(el).zIndex')
#     if z_index != 'auto' and int(z_index) < 0:
#         return False

#     bounding_box = await element.bounding_box()
#     if not bounding_box:
#         return False

#     viewport_size = await page.viewport_size()
#     if (
#         bounding_box['x'] + bounding_box['width'] < 0
#         or bounding_box['x'] > viewport_size['width']
#         or bounding_box['y'] + bounding_box['height'] < 0
#         or bounding_box['y'] > viewport_size['height']
#     ):
#         return False

#     return True



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


async def save_screenshot(url_list: list, save_dir="temp", width=500, height=None) -> list:
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
                print(f"Invalid URL skipped: {url}")
                continue

            domain = parsed_url.netloc.replace(".", "_")  # Generate a safe file name from the domain
            filename = f"{domain}.png"
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
                print(f"Failed to process {url}: {e}")
                url_list.remove(url)  # Remove from the list on failure

        await browser.close()

    return filelist




def print_content(content : Dict):
    if content['score'] > 0:
        print(f"Tag: {content['tag']}, Score: {content['score']}, id: {content['id']}")
        # print(f"children: {content['children']}")
        print(f"attributes: {content['attributes']}")
        print(f"Rect: {content['rect']}")
        print(f"depth: {content['depth']}")
        print(f"css_selector: {content['css_selector']}")
        # if len(content['children']) < 50 :
        #     print(f"text attributes: {content['text']}")
        if content['links'] :
            print(f"Links: {', '.join(content.get('links', []))}")
        else : print("no links found")
        print("----------------------------------------------------------")


# + ----------------------------------------------------------------
#  remove encoded chars
# + ----------------------------------------------------------------

def remove_encoded_chars(url):
    import re

    encoded_pattern = r'%[0-9A-F]{2}'
    cleaned_url = re.sub(encoded_pattern, '', url)
    return cleaned_url



def rescore_main_content(main_content : dict, driver= None):
    if not isinstance(main_content, dict):
        raise TypeError("main_content must be a dictionary")

    # メインコンテンツのサイズを取得
    main_rect = main_content.get("rect", {"x": 0, "y": 0, "width": 0, "height": 0})
    main_width = main_rect.get("width", 0)
    main_height = main_rect.get("height", 0)


    # メインコンテンツの子ノードを取得
    child_nodes = main_content.get("children", [])
    if not isinstance(child_nodes, list):
        # child_nodesがリストでない場合は空リストを使用
        child_nodes = []
        print("$not_child_node_")

    # 子ノードの情報を取得し、新しい辞書のリストを作成
    child_node_dicts = create_child_node_dicts(child_nodes)
    
    # 子ノードに対してスコアリングを行う
    scorer = MainContentScorer(child_node_dicts, main_width, main_height)

    scorer.score_parent_and_children(child_node_dicts)

    # スコアをチェック
    for node in child_node_dicts:
        print(f"Tag: {node['tag']}, Score: {node['score']}")

    # スコアの高い順に子ノードを並べ替える
    child_node_dicts.sort(key=lambda x: x["score"], reverse=True)

    return child_node_dicts

def create_child_node_dicts(child_nodes) -> list[Dict]:
    """
    与えられた子ノードのリストから、新しい辞書のリストを作成する

    Args:
        child_nodes (list): 子ノードのリスト

    Returns:
        list: 新しい辞書のリスト
    """
    child_node_dicts = []
    for child in child_nodes:
        # 子ノードの矩形情報を取得または初期化
        rect = child.get("rect", {"x": 0, "y": 0, "width": 0, "height": 0})
        
        # 子ノードの属性情報を取得または初期化
        attributes = {}
        if "attributes" in child:
            attributes = child["attributes"]
        
        # 新しい辞書を作成し、子ノードの情報を設定
        child_node_dict = {
            "tag": child["tag"],
            "id": child.get("id"),
            "attributes": attributes,
            "children": create_child_node_dicts(child.get("children", [])),  # 再帰的に子ノードを処理
            "rect": rect,
            "depth" : child.get("depth", 1),  # 深さを設定
            "score": 0,  # スコアを初期化
            "text" : child.get("text", []),  # テキスト情報を設定
            "links" : child.get("links", []),  # リンク情報を設定
        }
        
        # 新しい辞書をリストに追加
        child_node_dicts.append(child_node_dict)
    
    return child_node_dicts

# + ----------------------------------------------------------------
# + ----------------------------------------------------------------
def get_all_children(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Recursively collects all descendant nodes for a given node.

    Parameters:
    node (Dict[str, Any]): The node from which to collect all descendants.

    Returns:
    List[Dict[str, Any]]: A list of all descendant nodes.
    """
    if not isinstance(node, dict):
        return []

    children = node.get('children', [])
    all_children = []
    
    for child in children:
        all_children.append(child)
        all_children.extend(get_all_children(child))
    
    return all_children

def update_nodes_with_children(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
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

    return updated_nodes



async def detect_main_content(url: str, page: Page) -> List[Dict]:
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=10000)
        
        await page.wait_for_selector('body', state='attached', timeout=10000)
        
        try:
            await page.wait_for_load_state('networkidle', timeout=30000)
        except PlaywrightTimeoutError:
            print("Network did not become idle within 30 seconds, continuing anyway.")
        
        await page.set_viewport_size({"width": 1920, "height": 1080})

        dimensions = await page.evaluate('''() => {
            return {
                width: Math.max(document.body.scrollWidth, document.body.offsetWidth, document.documentElement.clientWidth, document.documentElement.scrollWidth, document.documentElement.offsetWidth),
                height: Math.max(document.body.scrollHeight, document.body.offsetHeight, document.documentElement.clientHeight, document.documentElement.scrollHeight, document.documentElement.offsetHeight)
            }
        }''')

        await page.set_viewport_size({"width": dimensions['width'], "height": dimensions['height']})

        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(2000)

        tree = await get_tree(page)
        
        if not tree:
            print("Error: Empty tree structure returned")
            return []

        tree = [tree]  # Convert tree to list[Dict]

        scorer = MainContentScorer(tree, dimensions['width'], dimensions['height'])
        candidates = scorer.find_candidates()

        # save_json(candidates, f"{__file__}.json")

        return candidates

    except PlaywrightTimeoutError:
        print(f"Timeout occurred while loading {url}")
        return []
    except Exception as e:
        print(f"An error occurred while processing {url}: {str(e)}")
        print("Traceback:")
        traceback.print_exc(file=sys.stdout)
        return []


def rescore_main_content_with_children(main_content : Dict, driver=None) -> list[Dict]:
    if not isinstance(main_content, dict):
        raise TypeError("main_content must be a dictionary")

    # メインコンテンツのサイズを取得
    main_rect = main_content.get("rect", {"x": 0, "y": 0, "width": 0, "height": 0})
    main_width = main_rect.get("width", 0)
    main_height = main_rect.get("height", 0)


    # 親ノードとその子ノードのlistを作成
    scorer_list = update_nodes_with_children(main_content)

    # 子ノードに対してスコアリングを行う
    scorer = MainContentScorer(scorer_list, main_width, main_height)

    # 親ノードとその子ノードのスコアを比較する
    scored_nodes = scorer.score_parent_and_children()

    # スコアをチェック
    # for node in scored_nodes:
    #     print(f"Tag: {node['tag']}, Score: {node['score']}")

    # スコアの高い順に子ノードを並べ替える
    scored_nodes.sort(key=lambda x: x["score"], reverse=True)

    return scored_nodes

# error chackintg 
def print_error_details(e):
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {str(e)}")
    print("Traceback:")
    traceback.print_exc(file=sys.stdout)


async def fetch_robots_txt(url):
    """Fetch robots.txt content from the target website"""
    parsed_url = urlparse(url)
    robots_url = urljoin(f"{parsed_url.scheme}://{parsed_url.netloc}", '/robots.txt')
    
    async with aiohttp.ClientSession() as session:
        async with session.get(robots_url) as response:
            if response.status == 200:
                return await response.text()
            return None

def is_scraping_allowed(robots_txt, target_path):
    """Check if scraping is allowed for the given path based on robots.txt"""
    from urllib.robotparser import RobotFileParser
    from io import StringIO

    robot_parser = RobotFileParser()
    robot_parser.parse(StringIO(robots_txt).readlines())
    
    # Check if we are allowed to scrape the target path
    return robot_parser.can_fetch("*", target_path)


async def test_main(url):       

    max_loop_count = 10

    async with async_playwright() as p:
        # Fetch robots.txt
        robots_txt = await fetch_robots_txt(url)
        
        if robots_txt:
            # Check if scraping is allowed
            parsed_url = urlparse(url)
            target_path = parsed_url.path or "/"
            
            if not is_scraping_allowed(robots_txt, target_path):
                print(f"Scraping is not allowed on this URL: {url}")
                return


        #browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        # page = await context.new_page()
        # page = await browser.new_page()

        try:
            main_contents = await detect_main_content(url, page)
            if not main_contents:
                print("No main content detected.")
                return None

            print("Top candidates:")
            for content in main_contents[:6]:
                print_content(content)

            if main_contents:
                main_contents = rescore_main_content_with_children(main_contents[0])

                print("pre content diff:")
                for content in main_contents[:2]:
                    print_content(content)

                loop_count = 0
                while True:
                    tmp_main_content = main_contents[0] if main_contents else None
                    if tmp_main_content is None:
                        break

                    main_contents = rescore_main_content_with_children(tmp_main_content)

                    if not main_contents:
                        break

                    print(f" tmp_main tag : {tmp_main_content['tag']} main tag : {main_contents[0]['tag']}")
                    print(f'tmp_candidates score : {tmp_main_content["score"]}  & main_contents {main_contents[0]["score"]}')
                    if tmp_main_content["score"] >= main_contents[0]["score"]:
                        break

                    loop_count += 1
                    if loop_count == max_loop_count:
                        print("error: loop count")
                        break

                print("Rescored child nodes:")
                for child in main_contents[:5]:
                    print_content(child)

                print("Selected main content:")
                print_content(tmp_main_content)

                return tmp_main_content
            else:
                print("No main content detected after initial search.")
                return None

        except Exception as e:
            print("An error occurred during test_main:")
            print_error_details(e)
            return None

        finally:
            await browser.close()

# async def choice_content(url: str, selector: str):
#     """
#     Scrapes a webpage and extracts a tree structure based on provided filters.

#     Args:
#         url (str): The URL of the page to scrape.
#         kwargs: Optional filters for the elements to extract (tag, id, attributes).

#     Returns:
#         Dict: A tree structure of the DOM elements matching the filters, or an empty dictionary if no match.
#     """
#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=True)
#         context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
#         page = await context.new_page()
        
#         try:
#             # Navigate to the page with longer timeout
#             await page.goto(url, wait_until='domcontentloaded', timeout=10000)
            
#             # Wait for initial page load
#             await page.wait_for_selector('body', state='attached', timeout=10000)
            
#             try:
#                 await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                
#                 await page.wait_for_load_state('domcontentloaded', timeout=10000)  # 
#                 # await page.wait_for_load_state('networkidle', timeout=10000)  # 

#             except PlaywrightTimeoutError:
#                 print("Network did not become idle within 10 seconds, continuing anyway.")

#             # Get page dimensions
#             dimensions = await page.evaluate('''() => {
#                 return {
#                     width: Math.max(document.body.scrollWidth, document.body.offsetWidth, 
#                                   document.documentElement.clientWidth, document.documentElement.scrollWidth, 
#                                   document.documentElement.offsetWidth),
#                     height: Math.max(document.body.scrollHeight, document.body.offsetHeight, 
#                                    document.documentElement.clientHeight, document.documentElement.scrollHeight, 
#                                    document.documentElement.offsetHeight)
#                 }
#             }''')

#             # Set viewport to full page size
#             await page.set_viewport_size({"width": dimensions['width'], "height": dimensions['height']})

#             # Scroll through the page to ensure all content is loaded
#             await page.evaluate('''
#                 async () => {
#                     await new Promise((resolve) => {
#                         let totalHeight = 0;
#                         const distance = 100;
#                         const timer = setInterval(() => {
#                             const scrollHeight = document.body.scrollHeight;
#                             window.scrollBy(0, distance);
#                             totalHeight += distance;
                            
#                             if(totalHeight >= scrollHeight){
#                                 clearInterval(timer);
#                                 resolve();
#                             }
#                         }, 100);
#                     });
#                 }
#             ''')

#             # # Extract parameters from kwargs
#             # tag = kwargs.get("tag")
#             # element_id = kwargs.get("id")
#             # attributes = kwargs.get("attributes", {})

#             # Build CSS selector
#             # selectors = []
#             # if tag:
#             #     selectors.append(tag)
#             # if element_id:
#             #     selectors.append(f"#{element_id}")
#             # if attributes:
#             #     for key, value in attributes.items():
#             #         selectors.append(f"[{key}='{value}']")
            
#             # selector = "".join(selectors) if selectors else "body"

#             # Wait for element with longer timeout
#             try:
#                 await page.wait_for_selector(selector, timeout=10000)
#             except PlaywrightTimeoutError:
#                 print(f"Timeout waiting for selector: {selector}")
#                 return {}

#             # Get tree structure
#             tree = await get_tree(page, selector=selector)
            
#             if not tree:
#                 print(f"No matching elements found for selector: {selector}")
#                 # Fall back to JavaScript evaluation for debugging
#                 element_exists = await page.evaluate(f'''
#                     () => {{
#                         const el = document.querySelector("{selector}");
#                         return el ? true : false;
#                     }}
#                 ''')
#                 print(f"Element exists according to JavaScript: {element_exists}")
            
#             return tree

#         except Exception as e:
#             print(f"Error during content extraction: {str(e)}")
#             traceback.print_exc()
#             return {}

#         finally:
#             await context.close()
#             await browser.close()

async def choice_content(url: str, selector: str):
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
            tree = await get_tree(page, selector=selector)
            if not tree:
                print(f"No matching elements found for selector: {selector}")
                return {}

            return tree

        except Exception as e:
            print(f"Error during content extraction: {str(e)}")
            return {}

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

    import datetime
    sta_sec = datetime.datetime.now()
    asyncio.run(test_main(url))
    end_sec = datetime.datetime.now()

    print(f"full proc {end_sec - sta_sec} seconds")

    choice_dict = {
        "id": "ld_blog_article_comment_entries",
        "tag": "ol",
        "attributes": {"id": "ld_blog_article_comment_entries"}
    }
    sta_sec = datetime.datetime.now()

    end_sec = datetime.datetime.now()
    ch_tree=  asyncio.run(choice_content(url,"div#article-body[id='article-body']"))
    print(ch_tree,type(ch_tree))
    if ch_tree is not None :
        content_hash_text = hashlib.sha256(str(ch_tree["links"]).encode()).hexdigest()
    
        print(content_hash_text)
        end_sec = datetime.datetime.now()
        print(f"select scan proc {end_sec - sta_sec} seconds")
    

    import datetime
    print(datetime.datetime.now())

    # import requests

    # response = requests.get(url)
    # last_modified = response.headers.get("Last-Modified")
    # print(last_modified)