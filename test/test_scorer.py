import pytest
from content_extractor.scorer import (
    calculate_depth_weight,
    is_main_element,
    is_valid_element,
    MainContentScorer
)
from content_extractor.dom_treeSt import DOMTreeSt, BoundingBox

# =================================================================
# scorer.py のテスト
#
# 参照: doc/test/test_design_content_extractor.md
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
    # 計算式: base * (factor ** (current / max))
    expected = 1.0 * (4.0 ** (2.5 / 5.0)) # 4.0 ** 0.5 = 2.0
    assert calculate_depth_weight(current_depth=2.5, max_depth=5, base_weight=1.0, weight_factor=4.0) == pytest.approx(2.0)

def test_calculate_depth_weight_exceeding_max():
    """深さが最大値を超えた場合をテストする。"""
    expected = 1.0 * (4.0 ** (6 / 5.0)) # 4.0 ** 1.2
    assert calculate_depth_weight(current_depth=6, max_depth=5, base_weight=1.0, weight_factor=4.0) == pytest.approx(expected)


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
    # 面積のチェック `area < 0.05` は、ピクセル値ではなく正規化された座標を想定しているように見える。
    # このテストは、非常に小さい面積を持つノードをテストする。
    node = DOMTreeSt(tag="div", rect=BoundingBox(x=0, y=0, width=0.2, height=0.2)) # area = 0.04
    assert is_valid_element(node) is False

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
    assert scorer_instance._score_text_length(node) < 0.1
