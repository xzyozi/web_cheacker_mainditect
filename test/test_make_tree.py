from unittest.mock import AsyncMock

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
import pytest

from content_extractor.make_tree import _COLLECT_DOM_TREE_JS, escape_css_identifier, make_css_selector, make_tree


def _raw_node(
    tag="div",
    node_id="",
    attributes=None,
    rect=None,
    text="",
    links=None,
    children=None,
):
    return {
        "tag": tag,
        "id": node_id,
        "attributes": attributes if attributes is not None else {},
        "rect": rect if rect is not None else {"x": 0, "y": 0, "width": 100, "height": 100},
        "text": text,
        "links": links if links is not None else [],
        "children": children if children is not None else [],
    }


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.wait_for_load_state.return_value = None
    return page


# --- Tests for make_tree ---


@pytest.mark.asyncio
async def test_make_tree_basic_dom_structure_single_evaluate(mock_page):
    """#89: page.evaluate を1回だけ呼び出して階層構造・座標・深さ・セレクタを復元する。"""
    mock_page.evaluate.return_value = _raw_node(
        tag="body",
        rect={"x": 0, "y": 0, "width": 1920, "height": 1080},
        text="  Body text  ",
        children=[
            _raw_node(
                tag="div",
                node_id="my-div",
                attributes={"id": "my-div", "class": "container"},
                rect={"x": 10, "y": 20, "width": 800, "height": 400},
                text="Div text",
                children=[
                    _raw_node(
                        tag="p",
                        rect={"x": 15, "y": 30, "width": 700, "height": 50},
                        text="Paragraph text",
                    )
                ],
            )
        ],
    )

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)

    mock_page.evaluate.assert_awaited_once_with(
        _COLLECT_DOM_TREE_JS,
        {"selector": "body", "includeChildren": True},
    )
    mock_page.query_selector.assert_not_called()

    assert tree is not None
    assert tree.tag == "body"
    assert tree.depth == 1
    assert tree.text == "Body text"
    assert tree.css_selector == "body"
    assert tree.rect.to_dict() == {"x": 0, "y": 0, "width": 1920, "height": 1080}
    assert len(tree.children) == 1

    div_node = tree.children[0]
    assert div_node.tag == "div"
    assert div_node.depth == 2
    assert div_node.id == "my-div"
    assert div_node.attributes == {"id": "my-div", "class": "container"}
    assert div_node.text == "Div text"
    assert div_node.css_selector == "div#my-div"
    assert div_node.rect.to_dict() == {"x": 10, "y": 20, "width": 800, "height": 400}
    assert len(div_node.children) == 1

    p_node = div_node.children[0]
    assert p_node.tag == "p"
    assert p_node.depth == 3
    assert p_node.text == "Paragraph text"
    assert p_node.css_selector == "p"
    assert len(p_node.children) == 0


@pytest.mark.asyncio
async def test_make_tree_extracts_links(mock_page):
    mock_page.evaluate.return_value = _raw_node(
        tag="body",
        text="Body text",
        links=["http://example.com/link1", "http://example.com/link2"],
    )

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)
    assert tree is not None
    assert tree.links == ["http://example.com/link1", "http://example.com/link2"]


@pytest.mark.asyncio
async def test_make_tree_include_children_false_passes_flag(mock_page):
    """#89: Quickスキャン向けに include_children=False を JS 側へ渡せること。"""
    mock_page.evaluate.return_value = _raw_node(
        tag="main",
        text="Quick target",
        links=["http://example.com/a"],
        children=[],
    )

    tree = await make_tree(mock_page, selector="main.content", wait_for_load=False, include_children=False)

    mock_page.evaluate.assert_awaited_once_with(
        _COLLECT_DOM_TREE_JS,
        {"selector": "main.content", "includeChildren": False},
    )
    assert tree is not None
    assert tree.tag == "main"
    assert tree.links == ["http://example.com/a"]
    assert tree.children == []


@pytest.mark.asyncio
async def test_make_tree_selector_parameter(mock_page):
    mock_page.evaluate.return_value = _raw_node(
        tag="section",
        node_id="specific-section",
        attributes={"id": "specific-section"},
        text="Specific Content",
    )

    tree = await make_tree(mock_page, selector="#specific-section", wait_for_load=False)
    mock_page.evaluate.assert_awaited_once_with(
        _COLLECT_DOM_TREE_JS,
        {"selector": "#specific-section", "includeChildren": True},
    )
    assert tree is not None
    assert tree.tag == "section"
    assert tree.id == "specific-section"
    assert tree.text == "Specific Content"
    assert tree.css_selector == "section#specific-section"


@pytest.mark.asyncio
async def test_make_tree_root_element_not_found_returns_none(mock_page):
    mock_page.evaluate.return_value = None
    tree = await make_tree(mock_page, selector="#non-existent", wait_for_load=False)
    assert tree is None


@pytest.mark.asyncio
async def test_make_tree_wait_for_load_true(mock_page):
    mock_page.evaluate.return_value = _raw_node(tag="body")

    tree = await make_tree(mock_page, selector="body", wait_for_load=True)
    assert tree is not None
    mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=30000)


@pytest.mark.asyncio
async def test_make_tree_wait_for_load_false(mock_page):
    mock_page.evaluate.return_value = _raw_node(tag="body")

    tree = await make_tree(mock_page, selector="body", wait_for_load=False)
    assert tree is not None
    mock_page.wait_for_load_state.assert_not_called()


@pytest.mark.asyncio
async def test_make_tree_networkidle_timeout_continues(mock_page):
    """networkidle 待機でタイムアウトしても警告のみで DOM 構築を続行する。"""
    mock_page.wait_for_load_state.side_effect = PlaywrightTimeoutError("timeout")
    mock_page.evaluate.return_value = _raw_node(tag="body", text="Content")

    tree = await make_tree(mock_page, selector="body", wait_for_load=True)
    assert tree is not None
    assert tree.text == "Content"


@pytest.mark.asyncio
async def test_make_tree_playwright_error_returns_none(mock_page):
    """PlaywrightError 発生時はログ出力して None を返す。"""
    mock_page.evaluate.side_effect = PlaywrightError("invalid selector")
    tree = await make_tree(mock_page, selector="div[", wait_for_load=False)
    assert tree is None


@pytest.mark.asyncio
async def test_make_tree_reraises_unexpected_exception(mock_page):
    """PlaywrightError 以外の予期せぬ例外は握りつぶさず再送出する。"""
    mock_page.evaluate.side_effect = RuntimeError("unexpected bug")
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
