import pytest
from unittest.mock import AsyncMock, MagicMock
from content_extractor.quality_evaluator import (
    is_no_results_page,
    _find_result_container,
    quantify_search_results
)
from content_extractor.dom_treeSt import DOMTreeSt

# =================================================================
# quality_evaluator.py のテスト
# =================================================================

# --- Fixtures ---

@pytest.fixture
def mock_page():
    """A mock for the Playwright Page object."""
    page = AsyncMock()
    # Default evaluate to False
    page.evaluate.return_value = False
    return page

@pytest.fixture
def dom_tree_with_no_results_keyword():
    """DOM tree containing a 'no results' keyword."""
    return DOMTreeSt(text="Sorry, no results found for your query.")

@pytest.fixture
def search_results_dom_tree():
    """A DOM tree fixture that mimics a search results page."""
    # Build from the inside out
    item1 = DOMTreeSt(tag='div', attributes={'class': 'result-item'}, links=['http://item1.com'], text="This is a valid result item with exactly ten words now.")
    item2 = DOMTreeSt(tag='div', attributes={'class': 'result-item'}, links=['http://item2.com'], text="This is another valid result item with more than ten words.")
    # Invalid item (not enough text)
    item3 = DOMTreeSt(tag='div', attributes={'class': 'result-item'}, links=['http://item3.com'], text="Short.")
    # Container with some other noise
    noise = DOMTreeSt(tag='div', attributes={'class': 'ad-container'})
    
    container = DOMTreeSt(tag='div', attributes={'class': 'results-list'}, children=[item1, item2, item3, noise])
    main_content = DOMTreeSt(tag='main', children=[container])
    return main_content


# --- Tests for is_no_results_page ---

@pytest.mark.asyncio
async def test_is_no_results_page_with_keyword(mock_page, dom_tree_with_no_results_keyword):
    """Test Case 1: Page with 'no results' keyword."""
    result = await is_no_results_page(mock_page, dom_tree_with_no_results_keyword)
    assert result is True

@pytest.mark.asyncio
async def test_is_no_results_page_with_selector(mock_page):
    """Test Case 2: Page with 'no results' selector."""
    dom_tree = DOMTreeSt(text="Some other text")
    # Simulate that the JS evaluation found a .no-results element
    mock_page.evaluate.side_effect = [True, False] # First call finds no-results, second finds no expected-results
    result = await is_no_results_page(mock_page, dom_tree)
    assert result is True
    assert mock_page.evaluate.call_count == 1 # Should short-circuit

@pytest.mark.asyncio
async def test_is_no_results_page_with_expected_selector(mock_page):
    """Test Case 3: Page with expected results selector should return False."""
    dom_tree = DOMTreeSt(text="Some other text")
    # Simulate JS evaluation: no 'no-results' selector, but 'expected-results' selector is found.
    mock_page.evaluate.side_effect = [False, True]
    result = await is_no_results_page(mock_page, dom_tree)
    assert result is False
    assert mock_page.evaluate.call_count == 2

@pytest.mark.asyncio
async def test_is_no_results_page_with_neither(mock_page):
    """Test Case 4: Page with neither keywords nor specific selectors."""
    dom_tree = DOMTreeSt(text="Some other text")
    # Both JS evaluations find nothing
    mock_page.evaluate.side_effect = [False, False]
    result = await is_no_results_page(mock_page, dom_tree)
    # If no expected container is found, it's considered a no-results page
    assert result is True
    assert mock_page.evaluate.call_count == 2

# --- Tests for _find_result_container ---

def test_find_result_container_finds_best_container(search_results_dom_tree):
    """Test Case 1: A container with many repeated class names."""
    container = _find_result_container(search_results_dom_tree)
    assert container is not None
    assert container.attributes.get('class') == 'results-list'

def test_find_result_container_no_clear_container():
    """Test Case 3: No clear container."""
    # A tree with no repeating sibling classes
    child1 = DOMTreeSt(tag='div', attributes={'class': 'item-a'})
    child2 = DOMTreeSt(tag='p', attributes={'class': 'item-b'})
    child3 = DOMTreeSt(tag='span', attributes={'class': 'item-c'})
    main_content = DOMTreeSt(tag='main', children=[child1, child2, child3])
    
    container = _find_result_container(main_content)
    assert container is None

# --- Tests for quantify_search_results ---

def test_quantify_search_results_with_valid_items(search_results_dom_tree):
    """Test Case 1: With a clear container and valid items."""
    result_node = quantify_search_results(search_results_dom_tree)
    # two items are valid (more than 10 words and a link)
    assert result_node.result_count == 2
    assert len(result_node.result_items) == 2
    assert result_node.result_items[0].text == "This is a valid result item with exactly ten words now."

def test_quantify_search_results_no_container():
    """Test Case 3: No container found."""
    child1 = DOMTreeSt(tag='div', attributes={'class': 'item-a'})
    main_content = DOMTreeSt(tag='main', children=[child1])
    
    result_node = quantify_search_results(main_content)
    assert result_node.result_count == 0
    assert result_node.result_items == []

def test_quantify_search_results_no_valid_items():
    """Test Case 2: With a container but no valid items."""
    item1 = DOMTreeSt(tag='div', attributes={'class': 'result-item'}, text="Short text")
    item2 = DOMTreeSt(tag='div', attributes={'class': 'result-item'}, text="Another short one")
    container = DOMTreeSt(tag='div', attributes={'class': 'results-list'}, children=[item1, item2])
    main_content = DOMTreeSt(tag='main', children=[container])

    result_node = quantify_search_results(main_content)
    assert result_node.result_count == 0
    assert result_node.result_items == []
