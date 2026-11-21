from unittest.mock import AsyncMock

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import pytest

from content_extractor.make_tree import escape_css_identifier, make_css_selector, make_tree


# Fixtures for Playwright mocks
@pytest.fixture
def mock_page():
    page = AsyncMock()
    # Mock wait_for_load_state to prevent it from hanging during tests
    page.wait_for_load_state.return_value = None
    return page


@pytest.fixture
def mock_element_handle():
    handle = AsyncMock()
    # Default return for evaluate to prevent errors if not specifically mocked
    handle.evaluate.return_value = True  # Assume document.body.contains(el) is true by default
    handle.bounding_box.return_value = {"x": 0, "y": 0, "width": 100, "height": 100}
    handle.query_selector_all.return_value = []
    return handle


@pytest.fixture
def mock_bounding_box_data():
    return {"x": 0, "y": 0, "width": 100, "height": 100}


# --- Tests for make_tree ---


@pytest.mark.asyncio
async def test_make_tree_basic_dom_structure(mock_page, mock_bounding_box_data):
    # Create mock ElementHandles for a simple DOM: body -> div -> p
    mock_body_handle = AsyncMock()
    mock_div_handle = AsyncMock()
    mock_p_handle = AsyncMock()

    # Configure mock_page to return the body handle
    mock_page.query_selector.return_value = mock_body_handle

    # Configure the body handle
    mock_body_handle.evaluate.side_effect = [
        True,  # document.body.contains(el) for body
        {"tag": "body", "id": "", "attributes": {}, "text": "Body text", "links": []},  # properties for body
    ]
    mock_body_handle.bounding_box.return_value = mock_bounding_box_data
    mock_body_handle.query_selector_all.return_value = [mock_div_handle]  # children of body

    # Configure the div handle
    mock_div_handle.evaluate.side_effect = [
        True,  # document.body.contains(el) for div
        {
            "tag": "div",
            "id": "my-div",
            "attributes": {"id": "my-div", "class": "container"},
            "text": "Div text",
            "links": [],
        },  # properties for div
    ]
    mock_div_handle.bounding_box.return_value = mock_bounding_box_data
    mock_div_handle.query_selector_all.return_value = [mock_p_handle]  # children of div

    # Configure the p handle
    mock_p_handle.evaluate.side_effect = [
        True,  # document.body.contains(el) for p
        {"tag": "p", "id": "", "attributes": {}, "text": "Paragraph text", "links": []},  # properties for p
    ]
    mock_p_handle.bounding_box.return_value = mock_bounding_box_data
    mock_p_handle.query_selector_all.return_value = []  # children of p

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)

    assert tree is not None
    assert tree.tag == "body"
    assert tree.css_selector == "body"
    assert len(tree.children) == 1

    div_node = tree.children[0]
    assert div_node.tag == "div"
    assert div_node.id == "my-div"
    assert div_node.attributes == {"id": "my-div", "class": "container"}
    assert div_node.text == "Div text"
    assert div_node.css_selector == "div#my-div"
    assert len(div_node.children) == 1

    p_node = div_node.children[0]
    assert p_node.tag == "p"
    assert p_node.text == "Paragraph text"
    assert p_node.css_selector == "p"
    assert len(p_node.children) == 0


@pytest.mark.asyncio
async def test_make_tree_extracts_links(mock_page, mock_bounding_box_data):
    mock_body_handle = AsyncMock()
    mock_page.query_selector.return_value = mock_body_handle

    mock_body_handle.evaluate.side_effect = [
        True,
        {
            "tag": "body",
            "id": "",
            "attributes": {},
            "text": "Body text",
            "links": ["http://example.com/link1", "http://example.com/link2"],
        },
    ]
    mock_body_handle.bounding_box.return_value = mock_bounding_box_data
    mock_body_handle.query_selector_all.return_value = []

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)
    assert tree is not None
    assert tree.links == ["http://example.com/link1", "http://example.com/link2"]


@pytest.mark.asyncio
async def test_make_tree_skips_elements_without_bounding_box(mock_page, mock_bounding_box_data):
    mock_body_handle = AsyncMock()
    mock_child_handle = AsyncMock()

    mock_page.query_selector.return_value = mock_body_handle
    mock_body_handle.evaluate.side_effect = [
        True,
        {"tag": "body", "id": "", "attributes": {}, "text": "Body text", "links": []},
    ]
    mock_body_handle.bounding_box.return_value = mock_bounding_box_data
    mock_body_handle.query_selector_all.return_value = [mock_child_handle]

    mock_child_handle.evaluate.side_effect = [
        True,
        {"tag": "div", "id": "", "attributes": {}, "text": "Hidden Div", "links": []},
    ]
    mock_child_handle.bounding_box.return_value = None  # Child has no bounding box

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)
    assert tree is not None
    assert tree.tag == "body"
    assert len(tree.children) == 0  # Child with no bounding box should be skipped


@pytest.mark.asyncio
async def test_make_tree_selector_parameter(mock_page, mock_bounding_box_data):
    mock_target_handle = AsyncMock()
    mock_page.query_selector.return_value = mock_target_handle

    mock_target_handle.evaluate.side_effect = [
        True,
        {
            "tag": "section",
            "id": "specific-section",
            "attributes": {"id": "specific-section"},
            "text": "Specific Content",
            "links": [],
        },
    ]
    mock_target_handle.bounding_box.return_value = mock_bounding_box_data
    mock_target_handle.query_selector_all.return_value = []

    tree = await make_tree(mock_page, selector="#specific-section", wait_for_load=False)
    assert tree is not None
    assert tree.tag == "section"
    assert tree.id == "specific-section"
    assert tree.text == "Specific Content"
    assert tree.css_selector == "section#specific-section"


@pytest.mark.asyncio
async def test_make_tree_root_element_not_found(mock_page):
    mock_page.query_selector.return_value = None
    tree = await make_tree(mock_page, selector="#non-existent", wait_for_load=False)
    assert tree is None


@pytest.mark.asyncio
async def test_make_tree_wait_for_load_true(mock_page):
    # Ensure query_selector returns a mock handle so make_tree proceeds
    mock_handle = AsyncMock()
    mock_handle.evaluate.side_effect = [
        True,
        {"tag": "body", "id": "", "attributes": {}, "text": "", "links": []},
    ]
    mock_handle.bounding_box.return_value = {"x": 0, "y": 0, "width": 100, "height": 100}
    mock_handle.query_selector_all.return_value = []
    mock_page.query_selector.return_value = mock_handle

    tree = await make_tree(mock_page, selector="body", wait_for_load=True)
    assert tree is not None
    mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=30000)


@pytest.mark.asyncio
async def test_make_tree_wait_for_load_false(mock_page):
    # Ensure query_selector returns a mock handle so make_tree proceeds
    mock_handle = AsyncMock()
    mock_handle.evaluate.side_effect = [
        True,
        {"tag": "body", "id": "", "attributes": {}, "text": "", "links": []},
    ]
    mock_handle.bounding_box.return_value = {"x": 0, "y": 0, "width": 100, "height": 100}
    mock_handle.query_selector_all.return_value = []
    mock_page.query_selector.return_value = mock_handle

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)
    assert tree is not None
    mock_page.wait_for_load_state.assert_not_called()


@pytest.mark.asyncio
async def test_make_tree_networkidle_timeout_continues(mock_page):
    """networkidle 待機でタイムアウトしても警告のみで DOM 構築を続行する。"""
    mock_page.wait_for_load_state.side_effect = PlaywrightTimeoutError("timeout")
    mock_handle = AsyncMock()
    mock_handle.evaluate.side_effect = [
        True,
        {"tag": "body", "id": "", "attributes": {}, "text": "Content", "links": []},
    ]
    mock_handle.bounding_box.return_value = {"x": 0, "y": 0, "width": 100, "height": 100}
    mock_handle.query_selector_all.return_value = []
    mock_page.query_selector.return_value = mock_handle

    tree = await make_tree(mock_page, selector="body", wait_for_load=True)
    assert tree is not None
    assert tree.text == "Content"


@pytest.mark.asyncio
async def test_make_tree_playwright_error_returns_none(mock_page):
    """PlaywrightError 発生時はログ出力して None を返す。"""
    mock_page.query_selector.side_effect = PlaywrightError("invalid selector")
    tree = await make_tree(mock_page, selector="div[", wait_for_load=False)
    assert tree is None


@pytest.mark.asyncio
async def test_make_tree_reraises_unexpected_exception(mock_page):
    """PlaywrightError 以外の予期せぬ例外は握りつぶさず再送出する。"""
    mock_page.query_selector.side_effect = RuntimeError("unexpected bug")
    with pytest.raises(RuntimeError, match="unexpected bug"):
        await make_tree(mock_page, selector="body", wait_for_load=False)


# --- Tests for make_css_selector ---


def test_make_css_selector_with_id():
    props = {"tag": "div", "id": "main-content", "attributes": {"class": "foo"}}
    assert make_css_selector(props) == "div#main-content"


def test_make_css_selector_with_classes_only():
    props = {"tag": "p", "id": "", "attributes": {"class": "text-center article-body"}}
    assert make_css_selector(props) == "p.text-center.article-body"


def test_make_css_selector_with_tag_only():
    props = {"tag": "span", "id": "", "attributes": {}}
    assert make_css_selector(props) == "span"


def test_make_css_selector_with_id_and_classes():
    props = {"tag": "a", "id": "unique-link", "attributes": {"class": "button primary"}}
    assert make_css_selector(props) == "a#unique-link"


def test_make_css_selector_empty_properties():
    props = {}
    assert make_css_selector(props) == ""


def test_make_css_selector_missing_tag():
    # As per make_tree, 'tag' should always be present and lowercased.
    # If not, the current implementation would lead to '#my-id' or '.my-class'
    # which is not a valid CSS selector if tag is completely absent.
    # However, make_tree ensures 'tag' is always available.
    # For robust unit testing, let's explicitly test an empty tag scenario.
    props = {"tag": "", "id": "my-id", "attributes": {"class": "my-class"}}
    assert make_css_selector(props) == "#my-id"


def test_make_css_selector_empty_tag_and_id():
    props = {"tag": "", "id": "", "attributes": {}}
    assert make_css_selector(props) == ""


def test_make_css_selector_class_with_multiple_spaces():
    props = {"tag": "div", "id": "", "attributes": {"class": "  class1   class2  "}}
    assert make_css_selector(props) == "div.class1.class2"


def test_make_css_selector_no_class_attribute():
    props = {"tag": "div", "id": "my-id", "attributes": {"style": "color: red;"}}
    assert make_css_selector(props) == "div#my-id"


# --- Tests for escape_css_identifier（CSS.escape と同じ規則） ---


@pytest.mark.parametrize(
    "value, expected",
    [
        ("main", "main"),  # 英数字・ハイフン・アンダースコアは、そのまま
        ("_x", "_x"),
        ("md:px-4", r"md\:px-4"),  # Tailwind のバリアント（コロン）
        ("w-1/2", r"w-1\/2"),  # スラッシュ
        ("a.b", r"a\.b"),  # ドット
        ("a b", r"a\ b"),  # 空白
        ("1abc", r"\31 abc"),  # 先頭の数字は、16進エスケープ（後ろに空白）
        ("-1abc", r"-\31 abc"),  # 先頭が "-" のとき、2文字目の数字
        ("-", r"\-"),  # "-" 単独
        ("日本語", "日本語"),  # 非ASCIIは、そのまま使える
    ],
)
def test_escape_css_identifier(value, expected):
    assert escape_css_identifier(value) == expected


def test_make_css_selector_escapes_id_starting_with_digit():
    """数字で始まる ID は、エスケープしないと無効なセレクタ（`#1abc`）になる。"""
    props = {"tag": "div", "id": "1abc", "attributes": {}}
    assert make_css_selector(props) == r"div#\31 abc"


def test_make_css_selector_escapes_tailwind_classes():
    """Tailwind のクラス名（コロン・スラッシュ）が、そのままセレクタに入っても有効になる。"""
    props = {"tag": "div", "id": "", "attributes": {"class": "w-1/2 md:px-4"}}
    assert make_css_selector(props) == r"div.w-1\/2.md\:px-4"
