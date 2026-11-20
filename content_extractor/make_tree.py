import asyncio
import logging
import sys
from typing import Any, Dict, Optional

from playwright.async_api import ElementHandle, Page, async_playwright

from .dom_treeSt import BoundingBox, DOMTreeSt

# Use standard logging practice; configuration should be at the application entry point.
logger = logging.getLogger(__name__)


async def make_tree(
    page: Page, selector: str = "body", wait_for_load: bool = True, timeout: int = 30000, debug: bool = True
) -> Optional[DOMTreeSt]:
    """
    Get DOM tree starting from a specific selector or body.
    Page.goto(url)後に使用
    """

    async def parse_element(el: ElementHandle, current_depth: int = 1) -> Optional[DOMTreeSt]:
        """
        HTML 要素とその子要素を再帰的に解析し、関連する詳細を抽出します。
        """
        if not el:
            return None

        try:
            # Element may be detached from the DOM, especially in dynamic pages.
            if not await el.evaluate("el => document.body.contains(el)"):
                return None

            try:
                bounding_box = await el.bounding_box()
                if not bounding_box:
                    # Skip elements that are not rendered (no bounding box)
                    return None
            except Exception as e:
                logger.debug(f"Could not get bounding box for an element, skipping it: {str(e)}")
                return None

            properties = await el.evaluate("""el => ({
                tag: el.tagName.toLowerCase(),
                id: el.id,
                attributes: Object.fromEntries(Array.from(el.attributes).map(attr => [attr.name, attr.value])),
                text: el.innerText || "",
                links: Array.from(el.getElementsByTagName('a')).map(a => a.href).filter(Boolean).sort()
            })""")

            css_selector = make_css_selector(properties)

            tree = DOMTreeSt(
                tag=properties["tag"],
                id=properties["id"],
                attributes=properties["attributes"],
                rect=BoundingBox(
                    x=bounding_box["x"],
                    y=bounding_box["y"],
                    width=bounding_box["width"],
                    height=bounding_box["height"],
                ),
                depth=current_depth,
                text=properties["text"].strip(),
                css_selector=css_selector,
                links=properties["links"],
            )

            children = await el.query_selector_all(":scope > *")
            for child in children:
                child_node = await parse_element(child, current_depth + 1)
                if child_node:  # Check for None
                    tree.add_child(child_node)

            return tree

        except Exception as e:
            logger.error(f"Error parsing element: {str(e)}")
            return None

    try:
        if wait_for_load:
            try:
                logger.debug("Waiting for network to be idle...")
                await page.wait_for_load_state("networkidle", timeout=timeout)
                logger.info("Network is idle.")
            except Exception as e:
                logger.warning(f"Network did not become idle within {timeout}ms: {str(e)}")

        root_element = await page.query_selector(selector)
        if not root_element:
            logger.error(f"Root element not found with selector: {selector}")
            return None

        return await parse_element(root_element)

    except Exception as e:
        logger.critical(f"Failed to create DOM tree for selector '{selector}': {str(e)}")
        return None


def escape_css_identifier(value: str) -> str:
    """CSS の識別子（ID・クラス名）をエスケープする。

    ブラウザの `CSS.escape()`（CSSOM の "serialize an identifier"）と同じ規則。
    数字で始まる ID（`1abc`）や、`w-1/2`・`md:px-4` のように記号を含むクラス名を、
    そのまま `#...` / `.....` に連結すると無効なセレクタになるため、必ず通す。
    """
    result = []
    length = len(value)
    for index, char in enumerate(value):
        code = ord(char)
        if code == 0:
            result.append("\ufffd")  # NULL は置換文字にする
        elif (0x01 <= code <= 0x1F) or code == 0x7F:
            result.append(f"\\{code:x} ")  # 制御文字は16進エスケープ（後ろに空白）
        elif index == 0 and "0" <= char <= "9":
            result.append(f"\\{code:x} ")  # 先頭の数字
        elif index == 1 and "0" <= char <= "9" and value[0] == "-":
            result.append(f"\\{code:x} ")  # 先頭が "-" のとき、2文字目の数字
        elif index == 0 and char == "-" and length == 1:
            result.append("\\-")  # "-" 単独
        elif code >= 0x80 or char in "-_" or char.isascii() and char.isalnum():
            result.append(char)  # そのまま使える文字（非ASCIIを含む）
        else:
            result.append(f"\\{char}")  # それ以外の記号は、バックスラッシュでエスケープ
    return "".join(result)


def make_css_selector(properties: Dict[str, Any]) -> str:
    """
    Generates a more stable CSS selector from element properties.
    Prioritizes ID, then classes. Avoids overly specific attribute selectors.
    ID・クラス名は CSS 識別子としてエスケープする。ページ内での一意性は、この関数では保証しない
    （呼び出し側が、実ページでヒット件数を確認して `nth-of-type` を足す）。
    """
    tag = properties.get("tag", "")
    element_id = properties.get("id", "")

    # ID is the most reliable selector.
    if element_id:
        return f"{tag}#{escape_css_identifier(element_id)}"

    selector = tag

    attributes = properties.get("attributes", {})
    class_name = attributes.get("class", "")
    if class_name and isinstance(class_name, str):
        # Filter out empty strings that can result from multiple spaces
        classes = filter(None, class_name.strip().split())
        class_selector = ".".join(escape_css_identifier(c) for c in classes)
        if class_selector:
            selector += f".{class_selector}"

    return selector


async def test_makeTree():
    """Standalone test function for make_tree."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        test_url = "https://example.com"
        await page.goto(test_url, wait_until="domcontentloaded")

        logger.info(f"--- Running test_makeTree on {test_url} ---")
        # Correctly pass the page object to make_tree
        dom_tree = await make_tree(page, selector="body", debug=False)

        if dom_tree:
            logger.info("Successfully created DOM tree. Root node info:")
            logger.info(f"Tag: {dom_tree.tag}, Children: {len(dom_tree.children)}")
        else:
            logger.error("Failed to create DOM tree.")

        await browser.close()
        logger.info("--- test_makeTree finished ---")


if __name__ == "__main__":
    # Basic logger setup for standalone execution
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # On Windows, ProactorEventLoop is required for Playwright's async operations
    # in some environments.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(test_makeTree())
