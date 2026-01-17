# `content_extractor` モジュール 詳細テスト設計書

## 1. 目的

`pytest`フレームワークを導入し、`content_extractor`モジュールの主要な機能に対するユニットテストおよびインテグレーションテストを整備する。これにより、コードの品質、正確性、堅牢性を担保し、将来のリファクタリングや機能追加を安全に行えるようにする。

## 2. 方針

- **テストフレームワーク:** `pytest` を使用する。非同期処理のテストには `pytest-asyncio` を利用する。
- **モック:** Playwrightや外部APIへの依存を切り離すため、`unittest.mock` を用いてモックオブジェクトを使用する。

## 3. テストケース詳細

### 3.1. `scorer.py` (ユニットテスト)

#### `_calculate_screen_occupancy_multiplier(occupancy_rate)`
- **目的:** 画面占有率に応じたスコア倍率が、ピーク値で最大になり、離れると減衰することを確認する。
- **Test Case 1: ピーク値**
    - **内容:** 占有率がピーク値(0.8)の場合。
    - **入力:** `occupancy_rate=0.8`
    - **期待値:** `1.0` (math.exp(0))
- **Test Case 2: ピークから離れた値**
    - **内容:** 占有率がピークから大きく外れた場合。
    - **入力:** `occupancy_rate=0.1`
    - **期待値:** `1.0`より大幅に低い正の値。
- **Test Case 3: ゼロ**
    - **内容:** 占有率が0の場合。
    - **入力:** `occupancy_rate=0.0`
    - **期待値:** `1.0`より大幅に低い正の値。

#### `_score_link_length(node)`
- **目的:** リンク数に応じてスコアが変動することを確認する。
- **Test Case 1: リンク数ゼロ**
    - **内容:** 本文の可能性が高い（スコア=0.1）。
    - **入力:** `DOMTreeSt(links=[])`
    - **期待値:** `0.1`
- **Test Case 2: リンク数が平均値**
    - **内容:** 最もスコアが高くなる。
    - **入力:** `DOMTreeSt(links=[""] * 6)` (MEAN=6)
    - **期待値:** `1.0`に近い値。
- **Test Case 3: リンク数が非常に多い**
    - **内容:** ナビゲーションの可能性が高い（スコアが低くなる）。
    - **入力:** `DOMTreeSt(links=[""] * 100)`
    - **期待値:** `0.0`に近い低いスコア。

#### `_score_text_length(node)`
- **目的:** テキスト長に応じてスコアが変動することを確認する。
- **Test Case 1: テキスト長ゼロ**
    - **内容:** スコアは0。
    - **入力:** `DOMTreeSt(text="")`
    - **期待値:** `0.0`
- **Test Case 2: テキスト長が平均値**
    - **内容:** 最もスコアが高くなる。
    - **入力:** `DOMTreeSt(text="a" * 50)` (MEAN=50)
    - **期待値:** `1.0`に近い値。
- **Test Case 3: テキスト長が非常に長い**
    - **内容:** スコアが低くなる。
    - **入力:** `DOMTreeSt(text="a" * 2000)`
    - **期待値:** `0.0`に近い低いスコア。

#### `calculate_depth_weight(current_depth)`
- **目的:** DOMの階層が深いほど高い重みが返されることを確認する。
- **Test Case 1: 浅い階層**
    - **入力:** `current_depth=0`
    - **期待値:** `1.0` (base_weight)
- **Test Case 2: 深い階層**
    - **入力:** `current_depth=5` (max_depth)
    - **期待値:** `4.0` (weight_factor)

#### `is_main_element(node)`
- **目的:** タグやIDから、ノードがメインコンテンツ要素のヒントを持つか判定する。
- **Test Case 1: `<main>`タグ**
    - **入力:** `DOMTreeSt(tag="main")`
    - **期待値:** `True`
- **Test Case 2: IDに"main"を含む**
    - **入力:** `DOMTreeSt(tag="div", attributes={"id": "main-content"})`
    - **期待値:** `True`
- **Test Case 3: 該当しない**
    - **入力:** `DOMTreeSt(tag="div", attributes={"id": "sub-content"})`
    - **期待値:** `False`

#### `is_valid_element(node)`
- **目的:** ノードがメインコンテンツ候補として有効か（除外タグでなく、小さすぎないか）を判定する。
- **Test Case 1: 有効なコンテナタグ**
    - **入力:** `DOMTreeSt(tag="div", rect=BoundingBox(width=100, height=100))`
    - **期待値:** `True`
- **Test Case 2: 無効なナビゲーションタグ**
    - **入力:** `DOMTreeSt(tag="nav", rect=BoundingBox(width=100, height=100))`
    - **期待値:** `False`
- **Test Case 3: 面積が小さすぎる**
    - **入力:** `DOMTreeSt(tag="div", rect=BoundingBox(width=1, height=1))`
    - **期待値:** `False`

---

### 3.2. `core.py` (インテグレーションテスト)

- **目的:** 複数モジュールが連携するフローを検証する。
- **Test Case 1: `extract_main_content` のコンテンツ絞り込み**
    - **内容:** `make_tree`が親子関係を持つノードツリーを返し、`scorer`が適切にスコアを付ける設定で、`while`ループが正しく子ノードに絞り込み、最終的にループを抜けることを確認する。
    - **モック対象:** `make_tree`, `rescore_main_content_with_children`
    - **期待値:** 最終的に最もスコアの高い子孫ノードが `final_content`として返される。

## 4. テストデータと実行

- **テストデータ:** `DOMTreeSt`と`BoundingBox`を`dataclass`からインポートし、テストケースごとにオブジェクトを生成して利用する。
- **実行方法:** プロジェクトのルートディレクトリで `pytest` を実行する。
