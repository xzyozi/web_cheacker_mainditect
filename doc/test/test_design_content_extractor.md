# `content_extractor` モジュール 詳細テスト設計書

## 1. 目的

`pytest`フレームワークを導入し、`content_extractor`モジュールの主要な機能に対するユニットテストおよびインテグレーションテストを整備する。これにより、コードの品質、正確性、堅牢性を担保し、将来のリファクタリングや機能追加を安全に行えるようにする。

## 2. 方針

### 2.1. 全体方針

- **テストフレームワーク:** `pytest` を使用する。非同期処理のテストには `pytest-asyncio` を利用する。
- **モック:** Playwrightや外部APIへの依存を切り離すため、`unittest.mock` を用いてモックオブジェクトを使用する。
- **テスト範囲:**
    - **ユニットテスト:** 計算ロジックやデータ変換など、単体で完結する純粋な関数を中心にテストする。
    - **インテグレーションテスト:** 複数のコンポーネントが連携するフロー（特に`core.py`）を対象とし、主要な機能を模倣（モック）しながら全体の流れを検証する。

## 3. テストケース詳細

### 3.1. `scorer.py` (ユニットテスト)

#### `calc_text_density(node)`
- **目的:** DOMノードの面積に対するテキスト長の密度を計算する。
- **Test Case 1: 通常ケース**
    - **内容:** テキストと面積を持つ通常のノード。
    - **入力:** `DOMTreeSt(text="Hello", bbox=BoundingBox(width=100, height=50))`
    - **期待値:** `5 / (100 * 50) = 0.001`
- **Test Case 2: テキストなし**
    - **内容:** テキストがないノード。
    - **入力:** `DOMTreeSt(text="", bbox=BoundingBox(width=100, height=50))`
    - **期待値:** `0.0`
- **Test Case 3: 面積ゼロ**
    - **内容:** 幅または高さがゼロのノード（ゼロ除算防止）。
    - **入力:** `DOMTreeSt(text="Hello", bbox=BoundingBox(width=100, height=0))`
    - **期待値:** `0.0`

#### `calc_position_score(node, viewport_width, viewport_height)`
- **目的:** 画面中央に近いほど高いスコアを出すガウス関数ベースの位置スコアを検証する。
- **Test Case 1: 画面中央**
    - **内容:** ビューポートのほぼ中央に配置されたノード。
    - **入力:** `node=DOMTreeSt(bbox=BoundingBox(x=860, y=440, width=200, height=200)), viewport_width=1920, viewport_height=1080`
    - **期待値:** `1.0`に近い高いスコア。
- **Test Case 2: 画面の端**
    - **内容:** ビューポートの左上に配置されたノード。
    - **入力:** `node=DOMTreeSt(bbox=BoundingBox(x=0, y=0, width=100, height=100)), viewport_width=1920, viewport_height=1080`
    - **期待値:** `0.0`に近い低いスコア。

#### `MainContentScorer.score_node(node)`
- **目的:** 各スコア計算関数を呼び出し、重み付けされた最終スコアを算出する処理を検証する。
- **Test Case 1: 総合スコア**
    - **内容:** `calc_text_density`や`calc_position_score`等をモック化し、それぞれが特定の値を返したときに、最終的な重み付けスコアが正しく計算されることを確認する。
    - **入力:** `node`オブジェクト。各スコア計算関数は`MagicMock`で特定の値（例: `0.5`）を返すように設定。
    - **期待値:** `(density_score * w_density) + (position_score * w_position) + ...` のように、設定された重みに基づく合計スコア。

---

### 3.2. `core.py` (インテグレーションテスト)

- **目的:** 複数モジュールが連携するフローを検証する。
- **Test Case 1: `extract_main_content` のコンテンツ絞り込み**
    - **内容:** `make_tree`が親子関係を持つノードツリーを返し、`scorer`が適切にスコアを付ける設定で、`while`ループが正しく子ノードに絞り込み、最終的にループを抜けることを確認する。
    - **モック対象:** `make_tree`, `rescore_main_content_with_children`
    - **期待値:** 最終的に最もスコアの高い子孫ノードが `final_content`として返される。

## 4. テストデータ

- ユニットテストには、`DOMTreeSt`と`BoundingBox`を`dataclass`からインポートし、テストケースごとにオブジェクトを生成して利用する。
- 必要に応じて、`pytest`のフィクスチャ機能（`@pytest.fixture`）を活用し、共通のテストデータを複数のテストで再利用する。

## 5. 実行方法

プロジェクトのルートディレクトリで以下のコマンドを実行し、テストを起動する。

```bash
pytest
```