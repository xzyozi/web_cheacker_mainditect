import pytest
from unittest.mock import MagicMock
from content_extractor.dom_treeSt import DOMTreeSt, BoundingBox
from content_extractor.dom_utils import flatten_dom_tree, rescore_main_content_with_children
from content_extractor.scorer import MainContentScorer

# --- Fixtures for DOMTreeSt ---

@pytest.fixture
def simple_dom_tree():
    # p1 (root)
    #   div1
    #     p2
    #   p3
    p2 = DOMTreeSt(tag='p', text='Paragraph 2', depth=2)
    div1 = DOMTreeSt(tag='div', text='Div 1', children=[p2], depth=1)
    p3 = DOMTreeSt(tag='p', text='Paragraph 3', depth=1)
    p1 = DOMTreeSt(tag='p', text='Paragraph 1', children=[div1, p3], depth=0)

    # Set parents for easier navigation and completeness, though not strictly needed for flatten_dom_tree
    div1.parent = p1
    p2.parent = div1
    p3.parent = p1

    return p1, div1, p2, p3

@pytest.fixture
def complex_dom_tree():
    # body
    #   header
    #   main
    #     article
    #       p1
    #       img
    #     aside
    #   footer
    body = DOMTreeSt(tag='body', depth=0)
    header = DOMTreeSt(tag='header', depth=1)
    main = DOMTreeSt(tag='main', depth=1)
    footer = DOMTreeSt(tag='footer', depth=1)
    article = DOMTreeSt(tag='article', depth=2)
    p1 = DOMTreeSt(tag='p', depth=3)
    img = DOMTreeSt(tag='img', depth=3)
    aside = DOMTreeSt(tag='aside', depth=2)

    body.add_child(header)
    body.add_child(main)
    body.add_child(footer)
    main.add_child(article)
    main.add_child(aside)
    article.add_child(p1)
    article.add_child(img)

    return body, header, main, footer, article, p1, img, aside


# --- Tests for flatten_dom_tree ---

def test_flatten_dom_tree_single_node():
    """Test Case 1: 単一ノードのツリー"""
    node = DOMTreeSt(tag='div')
    flattened = flatten_dom_tree(node)
    assert len(flattened) == 1
    assert flattened[0] is node

def test_flatten_dom_tree_simple_tree(simple_dom_tree):
    """Test Case 2: シンプルな親子関係"""
    p1, div1, p2, p3 = simple_dom_tree
    flattened = flatten_dom_tree(p1)
    # Expected DFS order: p1, div1, p2, p3
    assert flattened == [p1, div1, p2, p3]

def test_flatten_dom_tree_complex_tree(complex_dom_tree):
    """Test Case 3: 複数階層のツリー"""
    body, header, main, footer, article, p1, img, aside = complex_dom_tree
    flattened = flatten_dom_tree(body)
    # Expected DFS order
    expected_order = [body, header, main, article, p1, img, aside, footer]
    assert flattened == expected_order

def test_flatten_dom_tree_empty_children():
    """Test with a node that has an empty children list."""
    node = DOMTreeSt(tag='span', children=[])
    flattened = flatten_dom_tree(node)
    assert flattened == [node]

# --- Tests for rescore_main_content_with_children ---

def test_rescore_main_content_with_children_type_error():
    """Test Case 2: 無効な入力タイプ"""
    with pytest.raises(TypeError, match="main_content must be a DOMTreeSt"):
        rescore_main_content_with_children(None)
    with pytest.raises(TypeError, match="main_content must be a DOMTreeSt"):
        rescore_main_content_with_children("not a DOMTreeSt")

def test_rescore_main_content_with_children_basic_rescoring(mocker):
    """Test Case 1: 基本的な再スコアリングとソート"""
    # Create a dummy main_content node with some children
    child1 = DOMTreeSt(tag='div', score=10, rect=BoundingBox(0,0,10,10))
    child2 = DOMTreeSt(tag='p', score=20, rect=BoundingBox(0,0,10,10))
    main_content = DOMTreeSt(tag='article', children=[child1, child2], rect=BoundingBox(0,0,100,100))
    
    # Mock MainContentScorer.score_parent_and_children to return predefined scores
    mock_scorer_instance = MagicMock()
    # The list returned by score_parent_and_children should include main_content itself and its children,
    # with updated scores as if they were rescored.
    # We want child2 > main_content > child1 in final sort.
    mock_scorer_instance.score_parent_and_children.return_value = [
        DOMTreeSt(tag=child1.tag, score=5, rect=child1.rect), # Simulate rescoring
        DOMTreeSt(tag=main_content.tag, score=15, rect=main_content.rect),
        DOMTreeSt(tag=child2.tag, score=25, rect=child2.rect)
    ]
    mocker.patch('content_extractor.dom_utils.MainContentScorer', return_value=mock_scorer_instance)

    # Expected sorted order after rescoring
    # These also need to be new instances as they are compared with the ones returned by the mock.
    # Alternatively, we could assert on tags and scores separately.
    expected_sorted_nodes = [
        DOMTreeSt(tag=child2.tag, score=25, rect=child2.rect),
        DOMTreeSt(tag=main_content.tag, score=15, rect=main_content.rect),
        DOMTreeSt(tag=child1.tag, score=5, rect=child1.rect)
    ]

    # Capture the mock object created by patch for assertions on its calls
    mock_main_content_scorer_class = mocker.patch('content_extractor.dom_utils.MainContentScorer', return_value=mock_scorer_instance)

    result = rescore_main_content_with_children(main_content)

    assert [n.score for n in result] == [25, 15, 5]
    assert result[0].tag == 'p'
    assert result[1].tag == 'article'
    assert result[2].tag == 'div'
    
    mock_scorer_instance.score_parent_and_children.assert_called_once()
    # Assert on the mock class itself to check how it was instantiated
    mock_main_content_scorer_class.assert_called_once()
    assert isinstance(mock_main_content_scorer_class.call_args[0][0], list) # Check first arg (scorer_list)
    assert len(mock_main_content_scorer_class.call_args[0][0]) == 3 # main_content + 2 children

def test_rescore_main_content_with_children_no_children(mocker):
    """Test Case 3: 子ノードがない場合"""
    main_content = DOMTreeSt(tag='article', children=[], rect=BoundingBox(0,0,100,100), score=10)

    mock_scorer_instance = MagicMock()
    # If no children, score_parent_and_children might just return the main_content node itself, possibly with an updated score
    mock_scorer_instance.score_parent_and_children.return_value = [DOMTreeSt(tag=main_content.tag, score=12, rect=main_content.rect)]
    
    mock_main_content_scorer_class = mocker.patch('content_extractor.dom_utils.MainContentScorer', return_value=mock_scorer_instance)

    result = rescore_main_content_with_children(main_content)
    
    assert len(result) == 1
    assert result[0].tag == 'article'
    assert result[0].score == 12 # Ensure score is updated if rescoring happened
    
    mock_scorer_instance.score_parent_and_children.assert_called_once()
    # Assert on the mock class itself to check how it was instantiated
    mock_main_content_scorer_class.assert_called_once()
    assert isinstance(mock_main_content_scorer_class.call_args[0][0], list)
    assert len(mock_main_content_scorer_class.call_args[0][0]) == 1
    assert mock_main_content_scorer_class.call_args[0][0][0] is main_content

def test_rescore_main_content_with_children_empty_flattened_list(mocker):
    """Test with MainContentScorer returning an empty list (e.g., no valid candidates)."""
    main_content = DOMTreeSt(tag='article', children=[], rect=BoundingBox(0,0,100,100), score=10)

    mock_scorer_instance = MagicMock()
    mock_scorer_instance.score_parent_and_children.return_value = [] # Scorer returns empty
    
    mock_main_content_scorer_class = mocker.patch('content_extractor.dom_utils.MainContentScorer', return_value=mock_scorer_instance)

    result = rescore_main_content_with_children(main_content)
    assert result == []
    mock_scorer_instance.score_parent_and_children.assert_called_once()
    mock_main_content_scorer_class.assert_called_once() # Ensure it was called here too
