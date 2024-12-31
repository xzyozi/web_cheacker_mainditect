import math
from typing import Dict, List, Any, Union , Optional
from concurrent.futures import ThreadPoolExecutor
from scipy import stats
import os
import asyncio
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

import traceback
from scipy import stats
import numpy as np
from PIL import Image, ImageDraw
from urllib.parse import urlparse, urljoin
import aiohttp
import sys

import hashlib

import util_str

asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
# +----------------------------------------------------------------
# + Constant definition
# +----------------------------------------------------------------

# 特徴量の分布を定義します
X_DIST = stats.norm(0.5, 0.35)   # X軸の特徴量の分布
Y_DIST = stats.norm(0.5, 0.35)  # Y軸の特徴量の分布
WIDTH_DIST = stats.gamma(6.7, scale=0.11)  # 幅の特徴量の分布

# スコアリングの重みを定義します
WEIGHTS = {
    "x": 1,        # X軸の重み
    "y": 1,        # Y軸の重み
    "width": 1,  # 幅の重み
    "height": 1.5    # 高さの重み
}

# テキスト量のスコアリングに関する定数
TEXT_LENGTH_WEIGHT = 1.5  # テキスト量の重みの係数
TEXT_LENGTH_MEAN = 50    # 文字数の平均値
TEXT_LENGTH_STD_LOW = 40     # 文字数の標準偏差（平均未満の場合）
TEXT_LENGTH_STD_HIGH = 1000  # 文字数の標準偏差（平均以上の場合）


def score_text_length(node: Dict) -> float:
    """
    要素内のテキスト量に基づいてスコアを計算する関数

    Args:
        node (Dict): 要素の情報が格納された辞書

    Returns:
        float: テキスト量に基づくスコア
    """
    text_length = len(node.get("text", ""))  # 要素内のテキストの文字数を取得
    # print(f'id: {node.get("id")} text: {text_length}')    

    if text_length == 0: score = 0
    elif text_length <= TEXT_LENGTH_MEAN:
        # 平均未満の場合、低い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((text_length - TEXT_LENGTH_MEAN) / TEXT_LENGTH_STD_LOW) ** 2)
    else:
        # 平均以上の場合、高い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((text_length - TEXT_LENGTH_MEAN) / TEXT_LENGTH_STD_HIGH) ** 2)

    # スコアに重みを掛ける
    weighted_score = score ** TEXT_LENGTH_WEIGHT
    
    return weighted_score

# + ----------------------------------------------------------------
# + save json file
# + ---------------------------------------------------------------
import json
def save_json(data, file_path="./data/json.json") :
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# + ----------------------------------------------------------------
# + link count socering 
# + ----------------------------------------------------------------
LINK_LENGTH_WEIGHT = 1.0  # リンクの重みの係数
LINK_LENGTH_MEAN = 6    # 文字数の平均値
LINK_LENGTH_STD_LOW = 5     # 文字数の標準偏差
LINK_LENGTH_STD_HIGH = 30


def score_link_length(node: Dict) -> float:
    """
    要素内のlink量に基づいてスコアを計算する関数

    Args:
        node (Dict): 要素の情報が格納された辞書

    Returns:
        float: link量に基づくスコア
    """
    link_length = len(node.get("links", []))  # 要素内のlink数を取得
    # リンクがない場合、スコアを0にするのではなく0.1にするようにする
    # if text_length == 0:score = 0
    if link_length == 0:score = 0.1
    elif link_length <= LINK_LENGTH_MEAN:
        # 平均未満の場合、低い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((link_length - LINK_LENGTH_MEAN) / LINK_LENGTH_STD_LOW) ** 2)
    else:
        # 平均以上の場合、高い標準偏差を使用してスコアを計算
        score = math.exp(-0.5 * ((link_length - LINK_LENGTH_MEAN) / LINK_LENGTH_STD_HIGH) ** 2)

    # スコアに重みを掛ける
    weighted_score = score ** LINK_LENGTH_WEIGHT
    
    return weighted_score


# メインコンテンツ判定のための関数
def is_main_element(node: Dict) -> bool:
    tag = node["tag"].upper()
    if tag == "MAIN":
        return True
    if "id" in node["attributes"] and "main" in node["attributes"]["id"].lower():
        return True
    return False

def is_skippable(node: Dict) -> bool:
    if len(node["children"]) != 1:
        return False
    child = node["children"][0]
    skip_threshold = 5
    if (
        abs(node["rect"]["x"] - child["rect"]["x"]) < skip_threshold
        and abs(node["rect"]["y"] - child["rect"]["y"]) < skip_threshold
        and abs(node["rect"]["width"] - child["rect"]["width"]) < skip_threshold
        and abs(node["rect"]["height"] - child["rect"]["height"]) < skip_threshold
    ):
        return True
    return False

def is_valid_element(node: Dict) -> bool:
    tag = node["tag"].upper()
    invalid_tags = [
        "NAV",
        "ASIDE",
        "HEADER",
        "FOOTER",
        "H1",
        "H2",
        "H3",
        "H4",
        "H5",
        "H6",
        "P",
        "BLOCKQUOTE",
        "PRE",
        "A",
        "THEAD",
        "TFOOT",
        "TH",
        "DD",
        "DT",
        "MENU",
        "BODY",
        "HTML",
    ]
    if tag in invalid_tags:
        return False
    
    area = node["rect"]["width"] * node["rect"]["height"]
    if area < 0.05:
        return False
    return True


# + ----------------------------------------------------------------
# +  get tree structure
# + ----------------------------------------------------------------
async def is_html_element(el):
    try:
        # Check if the element has a tagName property
        tag_name = await el.evaluate('el => el.tagName')
        return True
    except:
        return False


async def get_tree(
    page: Page,
    selector: Optional[str] = None,
    wait_for_load: bool = True,
    timeout: int = 30000,
    debug: bool = True
) -> Dict:
    """
    Get DOM tree starting from a specific selector or body.
    
    Args:
        page: Playwright Page object
        selector: CSS selector to start tree from (optional)
        wait_for_load: Whether to wait for network idle
        timeout: Timeout in milliseconds for waiting
        debug: Whether to print debug information
    
    Returns:
        Dict representing the DOM tree
    """
    root = await page.query_selector('body')
    if not root:
        return {}

    async def parse_element(el, current_depth=1) -> Dict:
        """
        Recursively parses an HTML element and its children, extracting relevant details.

        Args:
            el: The HTML element to parse.
            current_depth (int): The current depth in the DOM tree.

        Returns:
            Dict: The parsed representation of the element and its children.
        """
    try:
        if debug:
            print(f"Searching for element with selector: {selector}")
            
            # 現在のページ内容の確認
            all_elements = await page.evaluate('''() => {
                const elements = document.querySelectorAll('*[id]');
                return Array.from(elements).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    id: el.id,
                    visible: el.offsetParent !== null,
                    rect: el.getBoundingClientRect().toJSON()
                }));
            }''')
            
            print("Found elements with IDs on page:")
            for el in all_elements:
                print(f"- {el['tag']}#{el['id']} (visible: {el['visible']})")

        if wait_for_load:
            try:
                print("Waiting for network idle...")
                await page.wait_for_load_state('networkidle', timeout=timeout)
                print("Network is idle")
            except Exception as e:
                print(f"Network did not become idle within {timeout}ms: {str(e)}")

        # Try to find element with JavaScript first
        if selector:
            exists_js = await page.evaluate(f'''() => {{
                const el = document.querySelector("{selector}");
                if (el) {{
                    return {{
                        exists: true,
                        tag: el.tagName.toLowerCase(),
                        id: el.id,
                        visible: el.offsetParent !== null,
                        rect: el.getBoundingClientRect().toJSON()
                    }};
                }}
                return {{ exists: false }};
            }}''')
            
            if debug:
                if exists_js.get('exists'):
                    print(f"Element found in DOM: {json.dumps(exists_js, indent=2)}")
                else:
                    print(f"Element not found in DOM: {selector}")

        # If selector is provided, try to find that element
        root = None
        if selector:
            try:
                print(f"Waiting for element to be visible: {selector}")
                root = await page.wait_for_selector(selector, timeout=timeout)
                if not root:
                    print(f"Element not found: {selector}")
                    return {}
            except Exception as e:
                print(f"Error finding element {selector}: {str(e)}")
                
                # Additional debug information
                if debug:
                    page_content = await page.content()
                    print(f"Current page title: {await page.title()}")
                    print(f"Current URL: {page.url}")
                    
                    # Check if element exists but is not visible
                    element_handle = await page.query_selector(selector)
                    if element_handle:
                        is_visible = await element_handle.is_visible()
                        print(f"Element exists but visible: {is_visible}")
                        
                        # Get element properties
                        properties = await element_handle.evaluate('''el => ({
                            offsetParent: el.offsetParent !== null,
                            display: window.getComputedStyle(el).display,
                            visibility: window.getComputedStyle(el).visibility,
                            opacity: window.getComputedStyle(el).opacity
                        })''')
                        print(f"Element properties: {json.dumps(properties, indent=2)}")
                
                return {}
        else:
            root = await page.query_selector('body')

        if not root:
            return {}

        async def parse_element(el, current_depth=1) -> Dict:
            if not el:
                return {}

            try:
                # Ensure element is still attached to DOM
                is_attached = await el.evaluate('el => document.body.contains(el)')
                if not is_attached:
                    return {}

                try:
                    bounding_box = await el.bounding_box()
                    if not bounding_box:
                        return {}
                except Exception as e:
                    print(f"Could not get bounding box: {str(e)}")
                    return {}

                # Get element properties
                properties = await el.evaluate('''el => ({
                    tag: el.tagName.toLowerCase(),
                    id: el.id,
                    attributes: Object.fromEntries(Array.from(el.attributes).map(attr => [attr.name, attr.value])),
                    text: el.innerText || "",
                    links: Array.from(el.getElementsByTagName('a')).map(a => a.href).filter(Boolean).sort()
                })''')

                css_selector = make_css_selector(properties)

                node = {
                    "tag": properties['tag'],
                    "id": properties['id'],
                    "attributes": properties['attributes'],
                    "children": [],
                    "rect": {
                        "x": bounding_box['x'],
                        "y": bounding_box['y'],
                        "width": bounding_box['width'],
                        "height": bounding_box['height'],
                    },
                    "depth": current_depth,
                    "text": properties['text'],
                    "score": 0,
                    "css_selector": css_selector,
                    "links": properties['links'],
                }

                # Get children
                children = await el.query_selector_all(':scope > *')
                for child in children:
                    child_node = await parse_element(child, current_depth + 1)
                    if child_node:
                        node["children"].append(child_node)

                return node

            except Exception as e:
                print(f"Error parsing element: {str(e)}")
                return {}

        return await parse_element(root)

    except Exception as e:
        print(f"Error in get_tree: {str(e)}")
        return {}

# + ----------------------------------------------------------------
# +  make css selector
# + ----------------------------------------------------------------
def make_css_selector(choice_dict : Dict) -> str:
    """
    Generate a CSS selector from a dictionary containing tag, id, attributes, and other properties.

    Args:
        choice_dict (dict): A dictionary with keys 'tag', 'id', 'attributes', 'text', 'links', etc.

    Returns:
        str: The generated CSS selector.
    """
    tag = choice_dict.get("tag", "")
    element_id = choice_dict.get("id", "")
    attributes = choice_dict.get("attributes", {})
    # text = choice_dict.get("text", "").strip()
    # links = choice_dict.get("links", [])

    selector = tag

    # Add ID if available
    if element_id:
        selector += f"#{element_id}"

    # Add class or other attributes
    class_name = attributes.get("class", "")
    if class_name:
        class_selector = ".".join(class_name.split())
        selector += f".{class_selector}"

    for attr, value in attributes.items():
        if attr != "class":  # Class is handled separately
            selector += f"[{attr}='{value}']"

    # Add additional filters (if applicable)
    # Note: These require post-processing in Playwright, as they are not valid CSS selectors.
    # if text:
    #     selector += f":contains('{text}')"
    # if links:
    #     href_filter = "[href='{0}']".format(links[0]) if links else ""
    #     selector += href_filter

    return selector

# + ----------------------------------------------------------------
# +  depth weight
# + ----------------------------------------------------------------
def calculate_depth_weight(current_depth : int , 
                           max_depth : int = 8,
                           base_weight :float =1.0 , 
                           weight_factor :float =6.0):
    """
    現在の階層レベルに基づいて depth の重みを計算する関数

    Args:
        current_depth (int): 現在の階層レベル
        max_depth (int): 最大の階層レベル (デフォルト: 8)
        base_weight (float): ベースの重み係数 (デフォルト: 1.0)
        weight_factor (float): 重み係数の増加率 (デフォルト: 4.0)

    Returns:
        float: 計算された depth の重み
    """
    # 最大深さと現在の深さの比率を計算
    depth_ratio = current_depth / max_depth

    weight = base_weight * (weight_factor ** depth_ratio)

    return weight

# メインコンテンツスコアリングクラス
class MainContentScorer:
    def __init__(self, tree: list[Dict], width: int, height: int):
        if isinstance(tree, list):
            self.tree = tree
        else:
            raise TypeError("tree must be a list of dicts")
        

        self.width = width
        self.height = height

        self.init_depth_flag = True
    

    def _calculate_screen_occupancy_multiplier(self, occupancy_rate: float, peak: float = 0.6, sigma: float = 0.3) -> float:
        """
        Calculate the score multiplier based on the screen occupancy rate using a Gaussian function.
        :param occupancy_rate: The rate of screen occupancy (0 to 1).
        :param peak: The peak point of the Gaussian curve (default is 0.9). 0.6 or 0.65
        :param sigma: The standard deviation of the Gaussian curve (default is 0.1).
        :return: The multiplier for the score.
        """
        exponent = -0.5 * ((occupancy_rate - peak) / sigma) ** 2
        return math.exp(exponent)



    def _score_node(self, node: Dict,
                     pre_mode : bool = False ,
                     depth_flag : bool = True,
                     maintag_addscore : bool = False,
                     ):
        if self.init_depth_flag :
            # 一番上のtreeを0にするために差分をとる
            self.parent_depth_diff = node["depth"] 
            self.init_depth_flag = False
            # print("★ top level depth")
            # print(f' parent depth diff : {self.parent_depth_diff}  , depth : {node["depth"]}')
            # print_content(node)

        score = 1
        """
        if pre_mode :
            if is_main_element(node) :
                score += 1
        """
        try:
            link_count = len(node.get("links", []))  # リンクの数を取得

            link_score = 0.2 * min(link_count, 5)

            score *= link_score
            
        except : 
            # print("not link")
            pass


            # Calculate the screen occupancy rate
        element_area = node["rect"]["width"] * node["rect"]["height"]
        page_area = self.width * self.height
        occupancy_rate = element_area / page_area
        multiplier = self._calculate_screen_occupancy_multiplier(occupancy_rate)
    

        score *= multiplier


        x = (node["rect"]["x"] + node["rect"]["width"] / 2) / self.width  # X座標を正規化
        if self.height != 0:
            y = node["rect"]["y"] / self.height  # Y座標を正規化
        else:
            y = 0  # heightが0の場合はyを0に設定
        w = node["rect"]["width"] / self.width  # 幅を正規化
        if self.height != 0:
            h = node["rect"]["height"] / self.height  # 高さを正規化
        else:
            h = 0  # heightが0の場合は高さを0に設定

        # 正規化された座標と寸法から、各要素のスコアを計算
        x_score = X_DIST.pdf(x) ** WEIGHTS["x"]
        y_score = Y_DIST.pdf(y) ** WEIGHTS["y"]
        w_score = WIDTH_DIST.pdf(w) ** WEIGHTS["width"]
        h_score = min(h, 0.9) ** WEIGHTS["height"]

        score *= x_score * y_score * w_score * h_score

        link_score = 1  # リンクのスコアを初期化
        """ before code 
        try:
            link_count = len(node.get("links", []))  # リンクの数を取得
            link_score *= 0.2 * min(link_count, 5)  # リンクのスコアを計算
        except:
            pass
        """
        link_count =  score_link_length(node)

        # text_score = score_text_length(node)  # テキスト量に基づくスコアを計算


        if depth_flag :
            # ネストが深いほどスコアを高く設定する
            depth_weight = calculate_depth_weight( node["depth"] - self.parent_depth_diff)  # 深さに基づく重みを計算
            score *= depth_weight  # スコアを計算
            # print("★  code passed to depth weight calculation " + str(depth_weight ) ) 
        
        node["score"] = score * link_score  # * text_score  # 総合スコアを計算


        if maintag_addscore :
            if is_main_element(node):
                node["score"] += 0.5



        """
        for child in node.get("children", []):  # 子要素を再帰的にスコアリング
            self._score_node(child)
        """


    def find_candidates(self) -> List[Dict]:
        # self.tree = [self.tree] # ルートノードを List[Dict] に変換
        # if type(self.tree) == dict :
        #     nodes = [self.tree] # ルートノードを List[Dict] に変換
        # else : nodes = self.tree

        nodes = self.tree
        candidates = []
        while nodes :
            node = nodes.pop(0)

            if is_valid_element(node):
                candidates.append(node)

            self._score_node(node, pre_mode=True, depth_flag=False, maintag_addscore=True) 
            # print(f"Scored node: {node['tag']}, Score: {node['score']}, Valid: {is_valid_element(node)}")  # デバッグ用の出力
            
            nodes.extend(node["children"])  # 子ノードを追加

        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        return candidates
    
    # scoring for children nodes
    def score_parent_and_children(self) -> list[Dict]: 
        """
        親ノードとその子ノードのスコアを計算する

        Args:

        Returns:
            scored_nodes (list[Dict]}: 親ノードとその子ノードのスコアリング結果を含む辞書のリスト
        """
        scored_nodes = []
        # self._score_node(parent_node)  # 親ノードのスコアを計算
        # scored_nodes.append(parent_node)  # 親ノードを追加

        # for child_node in parent_node.get("children", []):
        #     self._score_node(child_node)  # 子ノードのスコアを計算
        #     scored_nodes.append(child_node)  # 子ノードを追加

        for node in self.tree:
            self._score_node(node)
            scored_nodes.append(node) 

        scored_nodes.sort(key=lambda x: x["score"], reverse=True)

        return scored_nodes


async def is_visible_element(element, page: Page) -> bool:
    if not element:
        return False

    tag_name = await element.evaluate('el => el.tagName.toUpperCase()')
    if tag_name in ["META", "SCRIPT", "LINK", "STYLE", "IFRAME"]:
        return False

    is_visible = await element.is_visible()
    if not is_visible:
        return False

    opacity = await element.evaluate('el => window.getComputedStyle(el).opacity')
    if float(opacity) == 0:
        return False

    z_index = await element.evaluate('el => window.getComputedStyle(el).zIndex')
    if z_index != 'auto' and int(z_index) < 0:
        return False

    bounding_box = await element.bounding_box()
    if not bounding_box:
        return False

    viewport_size = await page.viewport_size()
    if (
        bounding_box['x'] + bounding_box['width'] < 0
        or bounding_box['x'] > viewport_size['width']
        or bounding_box['y'] + bounding_box['height'] < 0
        or bounding_box['y'] > viewport_size['height']
    ):
        return False

    return True



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


async def save_screenshot(url_list : list, save_dir="temp") -> list:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        filelist = []
        util_str.util_handle_path(save_dir)
        for url in url_list:
            try:
                # ページ移動と初期待機を簡略化
                await page.goto(url, wait_until='load', timeout=50000)

                domain = util_str.get_domain(url)
                filename = f"{domain}.png"
                filepath = os.path.join("temp",filename)

                filelist.append(filepath)

                await page.screenshot(path=filepath, full_page=True)

            except Exception as e:
                print(e)

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

def remove_duplicate_ports(port_list):
    """
    リストから重複したポートを削除する関数
    
    Args:
        port_list (list): ポート番号のリスト
        
    Returns:
        list: 重複を削除したポート番号のリスト
    """
    # セットを使って重複を削除
    unique_ports = set(port_list)
    
    # セットをリストに変換して返す
    return list(unique_ports)


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
    # scorer = MainContentScorer({"children": child_node_dicts, "rect": {"width": main_width, "height": main_height}}, main_width, main_height)
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


def get_subtree(node : Dict) -> list[Dict]:
    """
    指定されたノードとその子ノードの情報を再帰的に取得する関数。

    Args:
        node (dict): 取得対象のノード。

    Returns:
        list: ノードとその子ノードの情報を含む辞書のリスト。
    """
    subtree = []  # ノード自身をコピーして追加

    # 子ノードを再帰的に処理
    def recurse(n: Dict):
        current_node = n.copy()
        # Remove children from the current node to avoid infinite loops
        current_node.pop('children', None)

        # Add the current node to the subtree list
        subtree.append(current_node)
        
        # Check if the node has children
        if 'children' in n:
            for child in n['children']:
                recurse(child)
    
    recurse(node)
    return subtree

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