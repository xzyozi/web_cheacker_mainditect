import pytest
from content_extractor.web_type_chk import PageMonitor, WebTypeCHK, WebType
from content_extractor.dom_treeSt import DOMTreeSt

# =================================================================
# web_type_chk.py のテスト
# =================================================================

# --- Fixtures for test data ---

@pytest.fixture
def node_data_1():
    return DOMTreeSt(
        links=[
            "http://sample.com/def/page-1",
            "http://sample.com/def/page-2",
            "http://sample.com/def/page-10"
        ]
    )

@pytest.fixture
def node_data_2():
    return DOMTreeSt(
        links=[
            "http://sample.com/def/page-8",
            "http://sample.com/def/page-9",
            "http://sample.com/def/page-10"
        ]
    )

@pytest.fixture
def node_data_3():
    return DOMTreeSt(
        links=[
            "/articles/page/2",
            "/articles/page/4",
            "/articles/page/5",
        ]
    )

@pytest.fixture
def node_data_6():
    return DOMTreeSt(
        links=["http://sample.com/page-1", "http://sample.com/page-2"]
    )

@pytest.fixture
def node_data_no_links():
    """Fixture for a DOM tree with no links."""
    return DOMTreeSt(links=[])

# --- Tests for PageMonitor ---

def test_determine_watch_page_standard_pagination(node_data_1):
    """Test Case 1: Standard pagination, URL should be modified."""
    base_url_1 = "http://sample.com/def/page-1"
    monitor_1 = PageMonitor(base_url_1, node_data_1)
    expected_url_1 = "http://sample.com/def/page-10"
    actual_url_1 = monitor_1.determine_watch_page()
    assert actual_url_1 == expected_url_1

def test_determine_watch_page_on_last_page(node_data_2):
    """Test Case 2: On the last page, should return None."""
    base_url_2 = "http://sample.com/def/page-10"
    monitor_2 = PageMonitor(base_url_2, node_data_2)
    expected_url_2 = None
    actual_url_2 = monitor_2.determine_watch_page()
    assert actual_url_2 == expected_url_2

def test_determine_watch_page_relative_links(node_data_3):
    """Test Case 3: The 'page/page' bug case, URL should be modified correctly."""
    base_url_3 = "http://sample.com/articles/page/3"
    monitor_3 = PageMonitor(base_url_3, node_data_3)
    expected_url_3 = "http://sample.com/articles/page/5"
    actual_url_3 = monitor_3.determine_watch_page()
    assert actual_url_3 == expected_url_3

def test_determine_watch_page_base_not_paginated(node_data_6):
    """Test Case 4: Base URL is not a paginated URL."""
    base_url_6 = "http://sample.com/regular/article.html"
    monitor_6 = PageMonitor(base_url_6, node_data_6)
    expected_url_6 = None
    actual_url_6 = monitor_6.determine_watch_page()
    assert actual_url_6 == expected_url_6

# --- Tests for WebTypeCHK ---

def test_webtype_chk_integration(node_data_3):
    """Test Case 1: Next page exists."""
    base_url_3 = "http://sample.com/articles/page/3"
    expected_url_3 = "http://sample.com/articles/page/5"
    chk_4 = WebTypeCHK(base_url_3, node_data_3)
    web_type_4 = chk_4.webtype_chk()
    assert web_type_4 == "page_changer"
    assert chk_4.next_url == expected_url_3

def test_webtype_chk_on_last_page(node_data_2):
    """Test Case 2: Last page, but URL is paginated."""
    base_url_2 = "http://sample.com/def/page-10"
    chk_5 = WebTypeCHK(base_url_2, node_data_2)
    web_type_5 = chk_5.webtype_chk()
    assert web_type_5 == "page_changer"
    assert chk_5.next_url is None

def test_webtype_chk_not_paginated(node_data_6):
    """Test Case 3: Not paginated (with links)."""
    base_url_6 = "http://sample.com/regular/article.html"
    chk_6 = WebTypeCHK(base_url_6, node_data_6)
    web_type_6 = chk_6.webtype_chk()
    assert web_type_6 == "plane"
    assert chk_6.next_url is None

def test_webtype_chk_not_paginated_no_links(node_data_no_links):
    """Test Case 3: Not paginated (no links)."""
    base_url = "http://sample.com/regular/article.html"
    chk = WebTypeCHK(base_url, node_data_no_links)
    web_type = chk.webtype_chk()
    assert web_type == "plane"
    assert chk.next_url is None
