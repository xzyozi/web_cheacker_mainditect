import pytest
from content_extractor.scorer import (
    calculate_depth_weight,
    is_main_element
)
from content_extractor.dom_treeSt import DOMTreeSt

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
