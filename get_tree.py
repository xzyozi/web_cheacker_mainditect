from typing import Dict, List, Any, Union , Optional
from playwright.async_api import Page
import json



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
        page: Playwright ページオブジェクト
        selector: ツリーを開始する CSS セレクター (オプション)
        wait_for_load: ネットワークアイドルを待つかどうか
        timeout: 待ち時間のタイムアウト (ミリ秒単位)
        debug: デバッグ情報を表示するかどうか
    
    Returns:
        Dict : DOM 構造情報
    """
    root = await page.query_selector('body')
    if not root:
        return {}

    async def parse_element(el, current_depth=1) -> Dict:
        """
        HTML 要素とその子要素を再帰的に解析し、関連する詳細を抽出します。

        Args:
            el: 解析する HTML 要素。
            current_depth (int): DOM ツリーにおける現在の深さ。

        Returns:
            Dict: 要素とその子ノードをパースしたもの。
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
     tag, id, attributes, その他のプロパティを含む辞書から CSS セレクタを生成します

    Args:
        choice_dict (dict): キー 'tag', 'id', 'attributes', 'text', 'links' などを持つ辞書型

    Returns:
        str: 生成されたCSSセレクタ。
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