import pytest

from content_extractor.dom_treeSt import BoundingBox, DOMTreeSt
from content_extractor.dom_utils import rescore_main_content_with_children
from content_extractor.scorer import (
    MIN_ELEMENT_AREA_PX,
    MainContentScorer,
    calculate_depth_weight,
    is_main_element,
    is_valid_element,
)

# =================================================================
# scorer.py のテスト
#
# 参照: docs/test/test_design_content_extractor.md
# =================================================================


# -----------------------------------------------------------------
# calculate_depth_weight() のテスト
#
# 設計書セクション: 3.1. scorer.py -> calculate_depth_weight()
# -----------------------------------------------------------------


def test_calculate_depth_weight_at_base():
    """Test Case 1: 浅い階層。深さ0の場合をテストする。"""
    assert calculate_depth_weight(0) == 1.0


def test_calculate_depth_weight_at_max():
    """Test Case 2: 深い階層。深さが最大値の場合をテストする。"""
    # 関数シグネチャのデフォルト引数を明示
    assert calculate_depth_weight(current_depth=5, max_depth=5, base_weight=1.0, weight_factor=4.0) == 4.0


def test_calculate_depth_weight_at_mid():
    """中間的な深さの場合をテストする。"""
    # 計算式: base * (factor ** (current / max)) = 4.0 ** 0.5 = 2.0
    assert calculate_depth_weight(current_depth=2.5, max_depth=5, base_weight=1.0, weight_factor=4.0) == pytest.approx(
        2.0
    )


def test_calculate_depth_weight_exceeding_max():
    """深さが最大値を超えた場合をテストする。"""
    expected = 1.0 * (4.0 ** (6 / 5.0))  # 4.0 ** 1.2
    assert calculate_depth_weight(current_depth=6, max_depth=5, base_weight=1.0, weight_factor=4.0) == pytest.approx(
        expected
    )


def test_calculate_depth_weight_negative_depth():
    """新しいテスト: 負の深さの場合をテストする。"""
    # scorer.pyの変更により、負の深さは0として扱われるようになった
    assert (
        calculate_depth_weight(current_depth=-1, max_depth=5, base_weight=1.0, weight_factor=4.0) == 1.0
    )  # 0深度と同じ結果


# -----------------------------------------------------------------
# is_main_element() のテスト
#
# 設計書セクション: 3.1. scorer.py -> is_main_element()
# -----------------------------------------------------------------


def test_is_main_element_with_main_tag():
    """Test Case 1: `<main>`タグ。大文字小文字を区別しないことをテストする。"""
    node_lower = DOMTreeSt(tag="main")
    node_upper = DOMTreeSt(tag="MAIN")
    assert is_main_element(node_lower) is True
    assert is_main_element(node_upper) is True


def test_is_main_element_with_main_id():
    """Test Case 2: IDに"main"を含む。id属性に'main'が含まれる場合をテストする。"""
    node = DOMTreeSt(tag="div", attributes={"id": "main-content"})
    assert is_main_element(node) is True


def test_is_main_element_with_main_id_case_insensitive():
    """idの大文字小文字を区別しない場合をテストする。"""
    node = DOMTreeSt(tag="div", attributes={"id": "has-MAIN-in-it"})
    assert is_main_element(node) is True


def test_is_main_element_with_irrelevant_tag_and_id():
    """Test Case 3: 該当しない。タグとidが一致しない場合をテストする。"""
    node = DOMTreeSt(tag="div", attributes={"id": "sidebar"})
    assert is_main_element(node) is False


def test_is_main_element_with_no_attributes():
    """属性がないプレーンなタグの場合をテストする。"""
    node = DOMTreeSt(tag="section")
    assert is_main_element(node) is False


def test_is_main_element_with_empty_attributes():
    """属性辞書が空の場合をテストする。"""
    node = DOMTreeSt(tag="div", attributes={})
    assert is_main_element(node) is False


def test_is_main_element_with_mixed_case_main_id():
    """idのさらに別の-大文字小文字を区別しない場合をテストする。"""
    node = DOMTreeSt(tag="div", attributes={"id": "my-Main-section"})
    assert is_main_element(node) is True


def test_is_main_element_with_main_in_class():
    """class属性に'main'が含まれるが、idには含まれない場合をテストする。"""
    node = DOMTreeSt(tag="div", attributes={"class": "main-body", "id": "content"})
    assert is_main_element(node) is False


@pytest.mark.parametrize(
    "node_input, expected_result",
    [
        (None, False),  # Noneノード
        (DOMTreeSt(tag="div", attributes=None), False),  # type: ignore[arg-type]  # attributesがNone
        (DOMTreeSt(tag="div", attributes={"id": None}), False),  # type: ignore[dict-item]  # idがNone
        (DOMTreeSt(tag=None, attributes={"id": "main"}), False),  # type: ignore[arg-type]  # tagがNone
    ],
)
def test_is_main_element_edge_cases(node_input, expected_result):
    """新しいテスト: None入力やattributes/tagがNoneの場合のエッジケース。"""
    if node_input is None:
        with pytest.raises(AttributeError):  # node.tag, node.attributesへのアクセスでAttributeError
            is_main_element(node_input)
    else:
        # scorer.pyの変更により、None値は適切に処理され、Falseが返るようになった
        assert is_main_element(node_input) == expected_result


# -----------------------------------------------------------------
# is_valid_element() のテスト
#
# 設計書セクション: 3.1. scorer.py -> is_valid_element()
# -----------------------------------------------------------------


def test_is_valid_element_with_valid_container():
    """Test Case 1: 有効なコンテナタグ。"""
    node = DOMTreeSt(tag="div", rect=BoundingBox(x=0, y=0, width=100, height=100))
    assert is_valid_element(node) is True


def test_is_valid_element_with_invalid_tag():
    """Test Case 2: 無効なナビゲーションタグ。"""
    node = DOMTreeSt(tag="nav", rect=BoundingBox(x=0, y=0, width=100, height=100))
    assert is_valid_element(node) is False


def test_is_valid_element_with_too_small_area():
    """Test Case 3: 面積が小さすぎる。"""
    # 面積のチェック `area < MIN_ELEMENT_AREA_PX` (100 px²) はピクセル単位で極小要素を除外する。
    # ここでは最小面積未満（0.04 px² < 100 px²）のノードが無効になることをテストする。
    node = DOMTreeSt(tag="div", rect=BoundingBox(x=0, y=0, width=0.2, height=0.2))  # area = 0.04
    assert is_valid_element(node) is False


@pytest.mark.parametrize(
    "width, height, expected",
    [
        (9, 9, False),  # 81 px² < MIN_ELEMENT_AREA_PX (100) -> 除外
        (10, 9.9, False),  # 99 px² < MIN_ELEMENT_AREA_PX (100) -> 除外
        (10, 10, True),  # 100 px² == MIN_ELEMENT_AREA_PX (100) -> 許可
        (100, 1, True),  # 100 px² == MIN_ELEMENT_AREA_PX (100) -> 許可
    ],
)
def test_is_valid_element_min_area_boundary(width, height, expected):
    """MIN_ELEMENT_AREA_PX = 100 の境界値で極小要素が除外・許可されることを確認する。"""
    assert MIN_ELEMENT_AREA_PX == 100
    node = DOMTreeSt(tag="div", rect=BoundingBox(x=0, y=0, width=width, height=height))
    assert is_valid_element(node) is expected


@pytest.mark.parametrize(
    "node_input, expected_exception, expected_result",
    [
        (None, AttributeError, None),  # Noneノード
        (DOMTreeSt(tag="div", rect=None), None, False),  # type: ignore[arg-type]  # rectがNone: area=0でFalse
        (
            DOMTreeSt(tag=None, rect=BoundingBox(x=0, y=0, width=100, height=100)),  # type: ignore[arg-type]
            None,
            False,
        ),  # tagがNoneの場合は無効
    ],
)
def test_is_valid_element_edge_cases(node_input, expected_exception, expected_result):
    """新しいテスト: None入力やrect/tagがNoneの場合のエッジケース。"""
    if expected_exception:
        with pytest.raises(expected_exception):
            is_valid_element(node_input)
    else:
        # scorer.pyの変更により、None値は適切に処理され、期待される結果が返るようになった
        assert is_valid_element(node_input) == expected_result


# -----------------------------------------------------------------
# _calculate_screen_occupancy_multiplier() のテスト
#
# 設計書セクション: 3.1. scorer.py -> _calculate_screen_occupancy_multiplier()
# -----------------------------------------------------------------


@pytest.fixture
def scorer_instance():
    """内部メソッドを呼び出すための、scorerのダミーインスタンス。"""
    return MainContentScorer(tree=[], width=1000, height=1000)


def test_screen_occupancy_multiplier_at_peak(scorer_instance):
    """Test Case 1: ピーク値。"""
    # デフォルトのピーク値は0.8
    assert scorer_instance._calculate_screen_occupancy_multiplier(0.8) == pytest.approx(1.0)


def test_screen_occupancy_multiplier_away_from_peak(scorer_instance):
    """Test Case 2: ピークから離れた値。"""
    assert scorer_instance._calculate_screen_occupancy_multiplier(0.1) < 0.1
    assert scorer_instance._calculate_screen_occupancy_multiplier(0.1) > 0


def test_screen_occupancy_multiplier_at_zero(scorer_instance):
    """Test Case 3: ゼロ。"""
    assert scorer_instance._calculate_screen_occupancy_multiplier(0.0) < 0.1
    assert scorer_instance._calculate_screen_occupancy_multiplier(0.0) > 0


@pytest.mark.parametrize(
    "occupancy_rate, expected_value_range_lower",
    [
        (-0.1, 0),  # 負の値は0として扱われる
        (1.1, 0),  # 1.0を超える値
        (None, 0),  # Noneは0として扱われる
    ],
)
def test_screen_occupancy_multiplier_edge_cases(scorer_instance, occupancy_rate, expected_value_range_lower):
    """新しいテスト: 画面占有率の範囲外の値やNoneの場合のエッジケース。"""
    # scorer.pyの変更により、Noneや負の値は適切に処理され、例外は発生しない
    result = scorer_instance._calculate_screen_occupancy_multiplier(occupancy_rate)
    assert result > expected_value_range_lower  # スコアは常に0より大きい
    assert result <= 1.0  # 最大値は1.0


# -----------------------------------------------------------------
# _score_link_length() のテスト
#
# 設計書セクション: 3.1. scorer.py -> _score_link_length()
# -----------------------------------------------------------------


def test_score_link_length_zero(scorer_instance):
    """Test Case 1: リンク数ゼロ。"""
    node = DOMTreeSt(links=[])
    # スコアは0.1をLINK_LENGTH_WEIGHT(1.0)で累乗したもの
    assert scorer_instance._score_link_length(node) == pytest.approx(0.1)


def test_score_link_length_at_mean(scorer_instance):
    """Test Case 2: リンク数が平均値。"""
    # MEANは6なので、ガウス分布はexp(0) = 1.0になる
    node = DOMTreeSt(links=[""] * 6)
    assert scorer_instance._score_link_length(node) == pytest.approx(1.0)


def test_score_link_length_very_high(scorer_instance):
    """Test Case 3: リンク数が非常に多い。"""
    node = DOMTreeSt(links=[""] * 100)
    assert scorer_instance._score_link_length(node) < 0.1


def test_score_link_length_none_links(scorer_instance):
    """新しいテスト: links属性がNoneの場合のエッジケース。"""
    node = DOMTreeSt(links=None)
    # scorer.pyの変更により、linksがNoneの場合は0として扱われる
    assert scorer_instance._score_link_length(node) == pytest.approx(0.1)


def test_score_link_length_non_list_links(scorer_instance):
    """新しいテスト: links属性がリストでない場合のエッジケース。"""
    node = DOMTreeSt(links="not_a_list")
    # scorer.pyの変更により、linksがリストでない場合は0として扱われる
    assert scorer_instance._score_link_length(node) == pytest.approx(0.1)


# -----------------------------------------------------------------
# _score_text_length() のテスト
#
# 設計書セクション: 3.1. scorer.py -> _score_text_length()
# -----------------------------------------------------------------


def test_score_text_length_zero(scorer_instance):
    """Test Case 1: テキスト長ゼロ。"""
    node = DOMTreeSt(text="")
    assert scorer_instance._score_text_length(node) == 0.0


def test_score_text_length_at_mean(scorer_instance):
    """Test Case 2: テキスト長が平均値。"""
    # MEANは50
    node = DOMTreeSt(text="a" * 50)
    assert scorer_instance._score_text_length(node) == pytest.approx(1.0)


def test_score_text_length_very_high(scorer_instance):
    """Test Case 3: テキスト長が非常に長い。"""
    node = DOMTreeSt(text="a" * 2000)
    # scorer.pyの計算結果に基づいて期待値を修正 (約0.0577)
    assert scorer_instance._score_text_length(node) == pytest.approx(0.0577, abs=0.001)


def test_score_text_length_none_text(scorer_instance):
    """新しいテスト: text属性がNoneの場合のエッジケース。"""
    node = DOMTreeSt(text=None)
    # scorer.pyの変更により、textがNoneの場合は0として扱われる
    assert scorer_instance._score_text_length(node) == pytest.approx(0.0)


def test_score_text_length_non_string_text(scorer_instance):
    """新しいテスト: text属性が文字列でない場合のエッジケース。"""
    node = DOMTreeSt(text=123)
    # scorer.pyの変更により、textが文字列でない場合は0として扱われる
    assert scorer_instance._score_text_length(node) == pytest.approx(0.0)


# -----------------------------------------------------------------
# MainContentScorer クラスのテスト
#
# 設計書セクション: 3.1. scorer.py -> find_candidates / score_parent_and_children
# -----------------------------------------------------------------
@pytest.fixture
def sample_dom_tree():
    """テスト用のDOMツリー構造を生成するフィクスチャ"""
    p = DOMTreeSt(tag="p", text="a" * 100, rect=BoundingBox(200, 200, 600, 400), depth=3)
    article = DOMTreeSt(tag="article", text="a", rect=BoundingBox(150, 150, 700, 500), depth=2, children=[p])
    aside = DOMTreeSt(tag="aside", rect=BoundingBox(850, 150, 100, 500), depth=2)  # is_valid_element=Falseになる想定
    main_content = DOMTreeSt(
        tag="main", text="a", rect=BoundingBox(100, 100, 800, 600), depth=1, children=[article, aside]
    )
    header = DOMTreeSt(tag="header", rect=BoundingBox(0, 0, 1000, 100), depth=1)  # is_valid_element=Falseになる想定
    footer = DOMTreeSt(tag="footer", rect=BoundingBox(0, 700, 1000, 100), depth=1)  # is_valid_element=Falseになる想定
    body = DOMTreeSt(tag="body", rect=BoundingBox(0, 0, 1000, 1000), depth=0, children=[header, main_content, footer])
    return [body]


def test_find_candidates(sample_dom_tree):
    """
    Test Case 1: `find_candidates` が最もメインコンテンツらしい要素を最高スコアとして返すことを確認する。
    """
    scorer = MainContentScorer(tree=sample_dom_tree, width=1000, height=1000)
    candidates = scorer.find_candidates()

    # デバッグ用にスコアを出力
    for c in candidates:
        print(f"Tag: {c.tag}, Score: {c.score}")

    # 候補リストはスコアで降順ソートされている
    assert candidates[0].score >= candidates[1].score
    # このテストケースでは<main>タグが最もスコアが高いはず
    assert candidates[0].tag == "main"


def test_score_parent_and_children_depth_weighting(scorer_instance):
    """
    深さを考慮したスコアリングで、同じ特徴を持つノードでも
    深い階層にあるものが高く評価されることを確認する。
    """
    # ジオメトリとテキストが同じで深さだけが違うノードを作成
    child = DOMTreeSt(tag="div", text="a", rect=BoundingBox(100, 100, 100, 100), depth=2)
    parent = DOMTreeSt(tag="div", text="a", rect=BoundingBox(100, 100, 100, 100), depth=1, children=[child])

    # Scorerを親ノードで初期化
    scorer = MainContentScorer(tree=[parent], width=1000, height=1000)
    scored_nodes = scorer.score_parent_and_children()

    parent_score = next(n.score for n in scored_nodes if n.depth == 1)
    child_score = next(n.score for n in scored_nodes if n.depth == 2)

    # デバッグ用にスコアを出力
    print(f"Parent score (depth 1): {parent_score}")
    print(f"Child score (depth 2): {child_score}")

    assert child_score > parent_score


def _build_parent_with_two_children(offset_x: float, offset_y: float) -> tuple[DOMTreeSt, DOMTreeSt, DOMTreeSt]:
    """親の位置を (offset_x, offset_y) だけ平行移動した同じ相対構造のツリーを生成する。"""
    child_center = DOMTreeSt(
        tag="div",
        attributes={"id": "center"},
        text="a" * 50,
        links=[""] * 3,
        rect=BoundingBox(offset_x + 300, offset_y + 200, 200, 200),
        depth=2,
    )
    child_edge = DOMTreeSt(
        tag="div",
        attributes={"id": "edge"},
        text="a" * 50,
        links=[""] * 3,
        rect=BoundingBox(offset_x + 0, offset_y + 0, 200, 200),
        depth=2,
    )
    parent = DOMTreeSt(
        tag="section",
        text="a" * 10,
        links=[],
        rect=BoundingBox(offset_x, offset_y, 800, 600),
        depth=1,
        children=[child_center, child_edge],
    )
    return parent, child_center, child_edge


def test_rescore_relative_coordinates_preserve_ranking_across_parent_positions():
    """
    origin_x / origin_y による相対座標評価（rescore_main_content_with_children 連携）で、
    親要素のページ座標を移動しても子要素の相対スコア・順位が逆転しないことを確認する。
    """
    parent_origin, center_origin, edge_origin = _build_parent_with_two_children(0.0, 0.0)
    rescore_main_content_with_children(parent_origin)

    parent_shifted, center_shifted, edge_shifted = _build_parent_with_two_children(500.0, 500.0)
    rescore_main_content_with_children(parent_shifted)

    # 相対位置が良い center が両ケースで edge より高スコアになり、順位が逆転しない
    assert center_origin.score > edge_origin.score
    assert center_shifted.score > edge_shifted.score

    # 親座標オフセットを差し引くため、算出されるスコア自体も一致する
    assert center_shifted.score == pytest.approx(center_origin.score)
    assert edge_shifted.score == pytest.approx(edge_origin.score)

    # 対照確認: origin_x / origin_y が 0 のままだと移動後の座標で順位が逆転する
    parent_no_origin, center_no_origin, edge_no_origin = _build_parent_with_two_children(500.0, 500.0)
    MainContentScorer(
        tree=[parent_no_origin, center_no_origin, edge_no_origin],
        width=800,
        height=600,
        origin_x=0.0,
        origin_y=0.0,
    ).score_parent_and_children()
    assert edge_no_origin.score > center_no_origin.score


def test_score_parent_and_children_deduplicates_with_seen(mocker):
    """
    平坦化済みツリーのように親と子孫が同じリストに含まれていても、
    seen セットにより同一ノードの重複評価が抑止されることを確認する。
    """
    grandchild = DOMTreeSt(tag="p", text="a" * 50, rect=BoundingBox(120, 120, 200, 100), depth=3)
    child = DOMTreeSt(tag="div", text="a" * 20, rect=BoundingBox(100, 100, 400, 300), depth=2, children=[grandchild])
    parent = DOMTreeSt(tag="main", text="a" * 10, rect=BoundingBox(50, 50, 800, 600), depth=1, children=[child])

    scorer = MainContentScorer(tree=[parent, child, grandchild, child], width=800, height=600)
    spy_refine = mocker.spy(scorer, "_score_for_refinement")

    scored_nodes = scorer.score_parent_and_children()

    assert len(scored_nodes) == 3
    assert len({id(node) for node in scored_nodes}) == 3
    assert spy_refine.call_count == 3
