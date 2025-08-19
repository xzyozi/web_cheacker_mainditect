from typing import Dict, List, Any, Union

from .dom_treeSt import DOMTreeSt
from .scorer import MainContentScorer
from setup_logger import setup_logger

logger = setup_logger("dom_utils")

def print_content(content : DOMTreeSt) -> None:
    """デバッグ用にコンテンツの詳細情報をログに出力します。"""
    if content.score > 0:
        logger.info(f"Tag: {content.tag}, Score: {content.score}, id: {content.id}")
        logger.info(f"attributes: {content.attributes}")
        logger.info(f"Rect: {content.rect}")
        logger.info(f"depth: {content.depth}")
        logger.info(f"css_selector: {content.css_selector}")
        if content.links :
            logger.info(f"Links: {', '.join(content.links)}")
        else : logger.info("リンクは見つかりませんでした")
        logger.info("----------------------------------------------------------")

def update_nodes_with_children(data: Union[Dict[str, Any], List[Dict[str, Any]], DOMTreeSt]) -> Union[List[Dict[str, Any]], List[DOMTreeSt]]:
    """
    ノードを再帰的にたどり、すべての子孫ノードを含む平坦なリストを返します。

    Args:
        data (Union[Dict[str, Any], List[Dict[str, Any]], DOMTreeSt]): 処理対象のルートとなるノードデータ。

    Returns:
        Union[List[Dict[str, Any]], List[DOMTreeSt]]: すべてのノードを含むリスト。
    """
    updated_nodes = []

    if isinstance(data, list):
        for node in data:
            updated_nodes.extend(update_nodes_with_children(node))
    elif isinstance(data, dict):
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
    """
    メインコンテンツ候補とその子ノードを再評価し、スコアの高い順にソートしたリストを返します。

    Args:
        main_content (DOMTreeSt): 評価対象のメインコンテンツ候補ノード。
        driver: (未使用)

    Returns:
        list[DOMTreeSt]: 再評価され、スコアでソートされたノードのリスト。
    
    Raises:
        TypeError: main_contentがDOMTreeStでない場合に発生します。
    """
    if not isinstance(main_content, DOMTreeSt):
        raise TypeError("main_content must be a DOMTreeSt")

    main_rect = main_content.rect
    main_width = main_rect.width
    main_height = main_rect.height

    scorer_list = update_nodes_with_children(main_content)

    scorer = MainContentScorer(scorer_list, main_width, main_height)

    scored_nodes = scorer.score_parent_and_children()

    scored_nodes.sort(key=lambda x: x.score, reverse=True)

    return scored_nodes