from typing import List

from .dom_treeSt import DOMTreeSt
from .scorer import MainContentScorer
from setup_logger import setup_logger

logger = setup_logger("dom_utils")

def print_content(content: DOMTreeSt) -> None:
    """デバッグ用にコンテンツの詳細情報をログに出力します。"""
    if content.score > 0:
        logger.info(f"Tag: {content.tag}, Score: {content.score}, id: {content.id}")
        logger.info(f"attributes: {content.attributes}")
        logger.info(f"Rect: {content.rect}")
        logger.info(f"depth: {content.depth}")
        logger.info(f"css_selector: {content.css_selector}")
        links_str = f"Links: {', '.join(content.links)}" if content.links else "リンクは見つかりませんでした"
        logger.info(links_str)
        logger.info("----------------------------------------------------------")

def flatten_dom_tree(node: DOMTreeSt) -> List[DOMTreeSt]:
    """
    指定されたDOMTreeStノードをルートとして、すべての子孫ノードを含む平坦なリストを返します。
    """
    nodes = [node]
    for child in node.children:
        nodes.extend(flatten_dom_tree(child))
    return nodes

def rescore_main_content_with_children(main_content: DOMTreeSt) -> List[DOMTreeSt]:
    """
    メインコンテンツ候補とその子ノードを再評価し、スコアの高い順にソートしたリストを返します。

    Args:
        main_content (DOMTreeSt): 評価対象のメインコンテンツ候補ノード。

    Returns:
        List[DOMTreeSt]: 再評価され、スコアでソートされたノードのリスト。
    
    Raises:
        TypeError: main_contentがDOMTreeStでない場合に発生します。
    """
    if not isinstance(main_content, DOMTreeSt):
        raise TypeError("main_content must be a DOMTreeSt")

    main_rect = main_content.rect
    main_width = main_rect.width
    main_height = main_rect.height

    # ツリーをフラットなリストに変換
    scorer_list = flatten_dom_tree(main_content)

    scorer = MainContentScorer(scorer_list, main_width, main_height)

    scored_nodes = scorer.score_parent_and_children()

    scored_nodes.sort(key=lambda x: x.score, reverse=True)

    return scored_nodes
