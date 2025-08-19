from typing import Optional
from collections import Counter
from playwright.async_api import Page

from .dom_treeSt import DOMTreeSt
from .config import NO_RESULTS_CONFIG
from .dom_utils import update_nodes_with_children
from setup_logger import setup_logger

logger = setup_logger("quality_evaluator")

async def is_no_results_page(page: Page, dom_tree: DOMTreeSt) -> bool:
    """
    ページが「結果なし」ページであるかを高速で判定します。
    テキストキーワード、特定のCSSセレクタの存在、または期待される結果コンテナの不在をチェックします。
    """
    # 1. テキストベースの検出
    main_content_text = dom_tree.text.lower()
    for keyword in NO_RESULTS_CONFIG["keywords"]:
        if keyword.lower() in main_content_text:
            logger.info(f"「結果なし」キーワード '{keyword}' を検出しました。")
            return True

    # 2. HTML構造ベースの検出 (「結果なし」を示すセレクタの存在)
    for selector in NO_RESULTS_CONFIG["no_results_selectors"]:
        try:
            if await page.locator(selector).count() > 0:
                logger.info(f"「結果なし」セレクタ '{selector}' を検出しました。")
                return True
        except Exception as e:
            logger.debug(f"セレクタ '{selector}' のチェック中にエラー: {e}")
            continue

    # 3. HTML構造ベースの検出 (期待される結果コンテナの不在)
    for selector in NO_RESULTS_CONFIG["expected_results_selectors"]:
        if await page.locator(selector).count() > 0:
            return False

    return True

def _is_valid_result_item(item_node: DOMTreeSt) -> bool:
    """
    個々のノードが有効な検索結果アイテムであるかを検証します。
    - ハイパーリンクを1つ以上含んでいる
    - 10単語以上のテキストコンテンツを持つ
    """
    has_link = len(item_node.links) > 0
    has_enough_text = len(item_node.text.split()) >= 10
    return has_link and has_enough_text

def _find_result_container(main_content_node: DOMTreeSt) -> Optional[DOMTreeSt]:
    """
    メインコンテンツノードの子孫から、最も繰り返し構造を持つ要素を結果コンテナとして特定します。
    """
    best_container = None
    max_repetition_score = 0

    candidate_nodes = update_nodes_with_children(main_content_node)

    for node in candidate_nodes:
        if not node.children or len(node.children) < 2:
            continue

        class_counts = Counter(
            child.attributes.get('class') for child in node.children if child.attributes.get('class')
        )
        
        if not class_counts:
            continue

        most_common_class, count = class_counts.most_common(1)[0]
        repetition_score = count * (count / len(node.children))

        if repetition_score > max_repetition_score:
            max_repetition_score = repetition_score
            best_container = node
            
    return best_container

def quantify_search_results(main_content_node: DOMTreeSt) -> DOMTreeSt:
    """フェーズ2：検索結果アイテムの定量化を実行します。"""
    container = _find_result_container(main_content_node)

    if not container:
        logger.info("結果コンテナが見つかりませんでした。")
        main_content_node.result_count = 0
        main_content_node.result_items = []
        return main_content_node

    valid_items = [item for item in container.children if _is_valid_result_item(item)]
    main_content_node.result_items = valid_items
    main_content_node.result_count = len(valid_items)
    logger.info(f"有効な検索結果アイテムを {main_content_node.result_count} 件検出しました。")
    return main_content_node