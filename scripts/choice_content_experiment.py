"""DOM ツリー取得の実験コード（旧 test/test_choice_content.py）。

自動テストではない。pytest に収集されないよう、test/ から scripts/ に移した。
`python scripts/choice_content_experiment.py` で手動実行する。実在のサイトへアクセスするため、
実行前に対象 URL を確認すること。
"""

import asyncio
import json
import logging
from typing import Dict, Optional

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

# ログ設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def get_tree(
    page: Page, selector: Optional[str] = None, wait_for_load: bool = True, timeout: int = 30000, debug: bool = True
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
    try:
        if debug:
            logging.info(f"Searching for element with selector: {selector}")

            # 現在のページ内容の確認
            all_elements = await page.evaluate("""() => {
                const elements = document.querySelectorAll('*[id]');
                return Array.from(elements).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    id: el.id,
                    visible: el.offsetParent !== null,
                    rect: el.getBoundingClientRect().toJSON()
                }));
            }""")

            logging.info("Found elements with IDs on page:")
            for el in all_elements:
                logging.info(f"- {el['tag']}#{el['id']} (visible: {el['visible']})")

        if wait_for_load:
            try:
                logging.info("Waiting for network idle...")
                await page.wait_for_load_state("networkidle", timeout=timeout)
                logging.info("Network is idle")
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logging.warning(f"Network did not become idle within {timeout}ms: {str(e)}")

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
                if exists_js.get("exists"):
                    logging.info(f"Element found in DOM: {json.dumps(exists_js, indent=2)}")
                else:
                    logging.warning(f"Element not found in DOM: {selector}")

        # If selector is provided, try to find that element
        root = None
        if selector:
            try:
                logging.info(f"Waiting for element to be visible: {selector}")
                root = await page.wait_for_selector(selector, timeout=timeout)
                if not root:
                    logging.error(f"Element not found: {selector}")
                    return {}
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logging.error(f"Error finding element {selector}: {str(e)}")

                # Additional debug information
                if debug:
                    logging.debug(f"Current page title: {await page.title()}")
                    logging.debug(f"Current URL: {page.url}")

                    # Check if element exists but is not visible
                    element_handle = await page.query_selector(selector)
                    if element_handle:
                        is_visible = await element_handle.is_visible()
                        logging.debug(f"Element exists but visible: {is_visible}")

                        # Get element properties
                        properties = await element_handle.evaluate("""el => ({
                            offsetParent: el.offsetParent !== null,
                            display: window.getComputedStyle(el).display,
                            visibility: window.getComputedStyle(el).visibility,
                            opacity: window.getComputedStyle(el).opacity
                        })""")
                        logging.debug(f"Element properties: {json.dumps(properties, indent=2)}")

                return {}
        else:
            root = await page.query_selector("body")

        if not root:
            return {}

        async def parse_element(el, current_depth=1) -> Dict:
            if not el:
                return {}

            try:
                # Ensure element is still attached to DOM
                is_attached = await el.evaluate("el => document.body.contains(el)")
                if not is_attached:
                    return {}

                try:
                    bounding_box = await el.bounding_box()
                    if not bounding_box:
                        return {}
                except PlaywrightError as e:
                    logging.debug(f"Could not get bounding box: {str(e)}")
                    return {}

                # Get element properties
                properties = await el.evaluate("""el => ({
                    tag: el.tagName.toLowerCase(),
                    id: el.id,
                    attributes: Object.fromEntries(Array.from(el.attributes).map(attr => [attr.name, attr.value])),
                    text: el.innerText || "",
                    links: Array.from(el.getElementsByTagName('a')).map(a => a.href).filter(Boolean).sort()
                })""")

                node = {
                    "tag": properties["tag"],
                    "id": properties["id"],
                    "attributes": properties["attributes"],
                    "children": [],
                    "rect": {
                        "x": bounding_box["x"],
                        "y": bounding_box["y"],
                        "width": bounding_box["width"],
                        "height": bounding_box["height"],
                    },
                    "depth": current_depth,
                    "text": properties["text"],
                    "links": properties["links"],
                    "score": 0,
                }

                # Get children
                children = await el.query_selector_all(":scope > *")
                for child in children:
                    child_node = await parse_element(child, current_depth + 1)
                    if child_node:
                        node["children"].append(child_node)

                return node

            except PlaywrightError as e:
                logging.error(f"Error parsing element: {str(e)}")
                return {}

        return await parse_element(root)

    except PlaywrightError as e:
        logging.error(f"Error in get_tree: {str(e)}")
        return {}


async def ch_main(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # ページに移動
        await page.goto(url)

        # コメントエントリーの取得
        selector = "ol#ld_blog_article_comment_entries"
        # コメントエントリーの取得（より柔軟な設定で）
        tree = await get_tree(
            page,
            selector=selector,
            wait_for_load=True,
            timeout=30000,
            debug=True,  # デバッグ情報を有効化
        )

        # 結果の処理
        if tree:
            print("Found comment entries:")
            print(f"Tag: {tree['tag']}")
            print(f"ID: {tree['id']}")
            print(f"Number of children: {len(tree['children'])}")
        else:
            print("Comment entries not found")

        await browser.close()


if __name__ == "__main__":
    # 使用例
    url = "https://loopholes.site/"
    url = " https://mangakoma01.net/manga/zhou-shu-hui-zhana004"
    url = "http://animesoku.com/archives/38156477.html"

    # asyncio.run(test_main(url))
    choice_dict = {
        "id": "ld_blog_article_comment_entries",
        "tag": "ol",
        "attributes": {"id": "ld_blog_article_comment_entries"},
    }

    ch_tree = asyncio.run(ch_main(url))
    # print(ch_tree)

    import datetime

    print(datetime.datetime.now())
