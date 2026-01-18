import pytest
from unittest.mock import MagicMock, AsyncMock

from content_extractor.dom_treeSt import DOMTreeSt, BoundingBox
from content_extractor.core import extract_main_content

# =================================================================
# core.py のテスト
#
# 参照: doc/test/test_design_content_extractor.md
# =================================================================

# -----------------------------------------------------------------
# Test Case 1: `extract_main_content` の絞り込みループ
#
# 設計書セクション: 3.2. `core.py` (インテグレーションテスト)
# -----------------------------------------------------------------

@pytest.fixture
def mock_browser():
    """PlaywrightのBrowserオブジェクトのモックを返すフィクスチャ。"""
    return AsyncMock()

@pytest.fixture
def dom_tree_fixture():
    """
    テスト用のDOMツリー構造を生成するフィクスチャ。
    設計書に記載の構造をモデル化する。
    """
    # 子から親へ定義していく
    p_node = DOMTreeSt(tag='p', text='This is the real content.', score=95, depth=4)
    article_node = DOMTreeSt(tag='article', attributes={'id': 'main-article'}, score=70, depth=3, children=[p_node])
    nav_node = DOMTreeSt(tag='nav', score=10, depth=3) # is_valid=False になる想定
    main_node = DOMTreeSt(tag='main', score=0, depth=2, children=[article_node, nav_node])
    wrapper_node = DOMTreeSt(tag='div', attributes={'id': 'wrapper'}, score=80, depth=1, children=[main_node])
    body_node = DOMTreeSt(tag='body', score=0, depth=0, children=[wrapper_node])

    # 循環参照を簡易的に設定
    p_node.parent = article_node
    article_node.parent = main_node
    nav_node.parent = main_node
    main_node.parent = wrapper_node
    wrapper_node.parent = body_node

    # メインコンテンツの候補はwrapper_nodeとarticle_node
    # ただし、article_nodeの子であるp_nodeが最終的に選ばれることを期待する
    # find_candidates が返すのは wrapper_node と article_node で、wrapper_node のスコアが高い想定
    wrapper_node.score = 80
    article_node.score = 70

    return [body_node]


@pytest.mark.asyncio
async def test_extract_main_content_refinement_loop(mocker, mock_browser, dom_tree_fixture):
    """
    `extract_main_content`が、スコアの低い親からスコアの高い子孫へと
    正しくコンテンツを絞り込んでいくプロセスをテストする。
    """
    # ----- モックの設定 -----

    # 外部依存や副作用のある関数をモック化
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mock_page = AsyncMock()
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=mock_page)
    mocker.patch('content_extractor.core.adjust_page_view', new_callable=AsyncMock, return_value={'width': 1920, 'height': 1080})
    mocker.patch('content_extractor.core.make_tree', new_callable=AsyncMock, return_value=dom_tree_fixture[0]) # make_treeはリストではなく単一の木を返す
    mocker.patch('content_extractor.core.save_json') # JSON保存は無効化

    # `MainContentScorer` のモック
    mock_scorer_instance = MagicMock()
    wrapper_node = dom_tree_fixture[0].children[0]
    article_node = wrapper_node.children[0].children[0]
    initial_candidates = [wrapper_node, article_node]
    mock_scorer_instance.find_candidates.return_value = initial_candidates
    
    mock_scorer_class = mocker.patch('content_extractor.core.MainContentScorer')
    mock_scorer_class.return_value = mock_scorer_instance

    # `rescore_main_content_with_children` のモック
    p_node = article_node.children[0]
    
    # スコアを再設定して、テストの意図を明確にする
    article_node.score = 85 # wrapper(80)を上回る
    p_node.score = 95       # article(85)を上回る

    mock_rescore = mocker.patch(
        'content_extractor.core.rescore_main_content_with_children',
        side_effect=[
            [article_node], # 1回目 (wrapperの子) -> articleが最高スコア
            [p_node],       # 2回目 (articleの子) -> pが最高スコア
            []              # 3回目 (pの子) -> 子なしでループ終了
        ]
    )

    # ----- テスト対象関数の実行 -----
    final_content = await extract_main_content(url="http://mock.url", browser=mock_browser)

    # ----- アサーション -----

    assert final_content is not None
    assert final_content.tag == 'p'
    assert final_content.text == 'This is the real content.'
    
    # ループ後の最終スコアは `rescore` の結果に依存する
    assert final_content.score == 95

    # モックの呼び出し回数などを検証
    assert mock_rescore.call_count == 3
    mock_rescore.assert_any_call(wrapper_node)
    mock_rescore.assert_any_call(article_node)
    
    # 3回目の呼び出しは、2回目の勝者であるp_nodeに対して行われる
    mock_rescore.assert_any_call(p_node)
