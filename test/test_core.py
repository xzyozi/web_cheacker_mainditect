import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys

from content_extractor.dom_treeSt import DOMTreeSt, BoundingBox
from content_extractor.core import extract_main_content

# =================================================================
# core.py のテスト
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


@pytest.mark.asyncio
async def test_extract_main_content_robots_disallowed(mocker, mock_browser):
    """Test that extract_main_content returns None if robots.txt disallows scraping."""
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value="User-agent: *\nDisallow: /")
    mocker.patch('content_extractor.core.is_scraping_allowed', return_value=False)
    
    result = await extract_main_content(url="http://mock.url/some/path", browser=mock_browser)
    
    assert result is None

@pytest.mark.asyncio
async def test_extract_main_content_setup_page_fails(mocker, mock_browser):
    """Test that extract_main_content returns None if setup_page fails."""
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=None)
    
    result = await extract_main_content(url="http://mock.url", browser=mock_browser)
    
    assert result is None

@pytest.mark.asyncio
async def test_extract_main_content_make_tree_fails(mocker, mock_browser):
    """Test that extract_main_content returns None if make_tree fails."""
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mock_page = AsyncMock()
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=mock_page)
    mocker.patch('content_extractor.core.adjust_page_view', new_callable=AsyncMock, return_value={'width': 1920, 'height': 1080})
    mocker.patch('content_extractor.core.make_tree', new_callable=AsyncMock, return_value=None)
    
    result = await extract_main_content(url="http://mock.url", browser=mock_browser)
    
    assert result is None

@pytest.mark.asyncio
async def test_extract_main_content_no_candidates(mocker, mock_browser, dom_tree_fixture):
    """Test that extract_main_content returns None if no candidates are found."""
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mock_page = AsyncMock()
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=mock_page)
    mocker.patch('content_extractor.core.adjust_page_view', new_callable=AsyncMock, return_value={'width': 1920, 'height': 1080})
    mocker.patch('content_extractor.core.make_tree', new_callable=AsyncMock, return_value=dom_tree_fixture[0])
    
    mock_scorer_instance = MagicMock()
    mock_scorer_instance.find_candidates.return_value = [] # No candidates
    mock_scorer_class = mocker.patch('content_extractor.core.MainContentScorer')
    mock_scorer_class.return_value = mock_scorer_instance
    
    result = await extract_main_content(url="http://mock.url", browser=mock_browser)
    
    assert result is None


@pytest.mark.asyncio
async def test_extract_main_content_recursive_call(mocker, mock_browser, dom_tree_fixture):
    """Test that extract_main_content calls itself recursively if a new watch_url is found."""
    # This test is complex because it involves recursion of the function under test.
    # We will spy on the function and mock its dependencies for the recursive call.
    
    spy = mocker.spy(sys.modules[extract_main_content.__module__], 'extract_main_content')

    # Mock dependencies for the first call
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mock_page = AsyncMock()
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=mock_page)
    mocker.patch('content_extractor.core.adjust_page_view', new_callable=AsyncMock, return_value={'width': 1920, 'height': 1080})
    mocker.patch('content_extractor.core.make_tree', new_callable=AsyncMock, return_value=dom_tree_fixture[0])

    # Mock WebTypeCHK: first call returns a new URL, second call does not.
    mock_webtype_instance1 = MagicMock()
    mock_webtype_instance1.webtype_chk.return_value = "page_changer"
    mock_webtype_instance1.next_url = "http://mock.url/page/2"
    
    mock_webtype_instance2 = MagicMock()
    mock_webtype_instance2.webtype_chk.return_value = "page_changer"
    mock_webtype_instance2.next_url = None
    mocker.patch('content_extractor.core.WebTypeCHK', side_effect=[mock_webtype_instance1, mock_webtype_instance2])
    
    # Mock scorer for the recursive call to prevent further complex logic
    mock_scorer_instance = MagicMock()
    mock_scorer_instance.find_candidates.return_value = []
    mocker.patch('content_extractor.core.MainContentScorer', return_value=mock_scorer_instance)

    await extract_main_content(url="http://mock.url/page/1", browser=mock_browser)

    assert spy.call_count == 2
    spy.assert_called_with("http://mock.url/page/2", mock_browser, 1, arg_webtype="page_changer")

@pytest.mark.asyncio
async def test_extract_main_content_rescore_no_improvement(mocker, mock_browser, dom_tree_fixture):
    """Test that the rescoring loop terminates if the score does not improve."""
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mock_page = AsyncMock()
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=mock_page)
    mocker.patch('content_extractor.core.adjust_page_view', new_callable=AsyncMock, return_value={'width': 1920, 'height': 1080})
    mocker.patch('content_extractor.core.make_tree', new_callable=AsyncMock, return_value=dom_tree_fixture[0])
    mocker.patch('content_extractor.core.save_json')

    parent_node = dom_tree_fixture[0].children[0]
    parent_node.score = 90
    child_node = parent_node.children[0]
    child_node.score = 80

    mock_scorer_instance = MagicMock()
    mock_scorer_instance.find_candidates.return_value = [parent_node]
    mocker.patch('content_extractor.core.MainContentScorer', return_value=mock_scorer_instance)
    
    # rescore returns child with lower score, then empty list
    mocker.patch('content_extractor.core.rescore_main_content_with_children', side_effect=[[child_node], []])

    result = await extract_main_content(url="http://mock.url", browser=mock_browser)
    
    # The loop should find child's score (80) is not > parent's (90), so it breaks.
    # The returned content should be the parent from before the break.
    assert result is parent_node

@pytest.mark.asyncio
async def test_extract_main_content_rescore_max_loops(mocker, mock_browser, dom_tree_fixture):
    """Test that the rescoring loop terminates at max_loop_count."""
    mocker.patch('content_extractor.core.fetch_robots_txt', new_callable=AsyncMock, return_value=None)
    mock_page = AsyncMock()
    mocker.patch('content_extractor.core.setup_page', new_callable=AsyncMock, return_value=mock_page)
    mocker.patch('content_extractor.core.adjust_page_view', new_callable=AsyncMock, return_value={'width': 1920, 'height': 1080})
    mocker.patch('content_extractor.core.make_tree', new_callable=AsyncMock, return_value=dom_tree_fixture[0])
    mocker.patch('content_extractor.core.save_json')

    nodes = [DOMTreeSt(tag=f'div{i}', score=80 + i) for i in range(10)]
    for i in range(9):
        nodes[i].children = [nodes[i+1]]

    mock_scorer_instance = MagicMock()
    mock_scorer_instance.find_candidates.return_value = [nodes[0]]
    mocker.patch('content_extractor.core.MainContentScorer', return_value=mock_scorer_instance)

    # rescore will always return the next child with a higher score
    mocker.patch('content_extractor.core.rescore_main_content_with_children', side_effect=[[n] for n in nodes[1:]])

    result = await extract_main_content(url="http://mock.url", browser=mock_browser)

    # The loop runs 5 times, `tmp_main_content` is updated 5 times.
    # On 6th iteration, loop_count is 5, loop breaks.
    # The content is from the 5th iteration, which is nodes[5].
    assert result.tag == 'div5'