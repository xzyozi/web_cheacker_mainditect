import asyncio
import logging
import sys
from typing import Any, Dict, Optional

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .dom_treeSt import BoundingBox, DOMTreeSt

# Use standard logging practice; configuration should be at the application entry point.
logger = logging.getLogger(__name__)

# 1回の page.evaluate で可視要素のDOMツリー全体（または単一ノード）を収集するJS。
# Playwright の el.bounding_box() と揃えるため、getBoundingClientRect()（ビューポート相対座標）と
# getClientRects().length > 0 / 幅・高さ > 0 で非描画要素を除外する。
_COLLECT_DOM_TREE_JS = """
({ selector, includeChildren }) => {
    const root = document.querySelector(selector);
    if (!root) {
        return null;
    }

    const collectNode = (el) => {
        if (!el || !document.body || !document.body.contains(el)) {
            return null;
        }
        const rect = el.getBoundingClientRect();
        if (!rect || rect.width <= 0 || rect.height <= 0 || el.getClientRects().length === 0) {
            return null;
        }

        const attributes = {};
        for (const attr of el.attributes) {
            attributes[attr.name] = attr.value;
        }

        const links = Array.from(el.getElementsByTagName("a"))
            .map((a) => (typeof a.href === "string" ? a.href : ""))
            .filter(Boolean)
            .sort();

        const children = [];
        if (includeChildren) {
            for (const child of el.children) {
                const childNode = collectNode(child);
                if (childNode !== null) {
                    children.push(childNode);
                }
            }
        }

        return {
            tag: (el.tagName || "").toLowerCase(),
            id: el.id || "",
            attributes,
            rect: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
            },
            text: typeof el.innerText === "string" ? el.innerText : "",
            links,
            children,
        };
    };

    return collectNode(root);
}
"""


def _build_dom_tree(raw: Dict[str, Any], current_depth: int = 1) -> DOMTreeSt:
    """JS から返された辞書ツリーを再帰的に DOMTreeSt へ変換する。"""
    rect_data = raw.get("rect") or {}
    css_selector = make_css_selector(raw)
    node = DOMTreeSt(
        tag=raw.get("tag", ""),
        id=raw.get("id", ""),
        attributes=raw.get("attributes") or {},
        rect=BoundingBox(
            x=rect_data.get("x", 0),
            y=rect_data.get("y", 0),
            width=rect_data.get("width", 0),
            height=rect_data.get("height", 0),
        ),
        depth=current_depth,
        text=(raw.get("text") or "").strip(),
        css_selector=css_selector,
        links=list(raw.get("links") or []),
    )
    for child_raw in raw.get("children") or []:
        if isinstance(child_raw, dict):
            node.add_child(_build_dom_tree(child_raw, current_depth + 1))
    return node


async def make_tree(
    page: Page,
    selector: str = "body",
    wait_for_load: bool = True,
    timeout: int = 30000,
    debug: bool = True,
    include_children: bool = True,
) -> Optional[DOMTreeSt]:
    """
    指定セレクタ（既定 `body`）を起点に DOM ツリーを一括 JS 実行で構築する。
    `include_children=False` の場合はルート要素 1 ノード分のみ収集する（Quick スキャン向け）。
    """
    _ = debug  # 後方互換のため引数を維持
    try:
        if wait_for_load:
            try:
                logger.debug("Waiting for network to be idle...")
                await page.wait_for_load_state("networkidle", timeout=timeout)
                logger.info("Network is idle.")
            except (PlaywrightTimeoutError, PlaywrightError) as e:
                logger.warning(f"Network did not become idle within {timeout}ms: {str(e)}")

        raw_tree = await page.evaluate(
            _COLLECT_DOM_TREE_JS,
            {"selector": selector, "includeChildren": include_children},
        )
        if not isinstance(raw_tree, dict):
            logger.error(f"Root element not found with selector: {selector}")
            return None

        return _build_dom_tree(raw_tree)

    except PlaywrightError as e:
        logger.critical(f"Failed to create DOM tree for selector '{selector}': {str(e)}")
        return None
    except Exception:
        logger.exception(f"Unexpected error creating DOM tree for selector '{selector}'")
        raise


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
