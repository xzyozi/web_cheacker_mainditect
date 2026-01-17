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

#### `find_candidates()`
- **目的:** `MainContentScorer`がDOMツリーからメインコンテンツの候補を正しく抽出し、スコア順にソートすることを確認する。
- **Test Case 1: 候補の抽出と順序**
    - **内容:** `is_valid_element`で除外されるべきノード（`<header>`, `<footer>`, `<aside>`など）が候補に含まれず、メインコンテンツ（`<main>`）が最も高いスコアを持つことを確認する。
    - **入力:** ヘッダー、メイン、フッター、記事、段落などを含む典型的なDOMツリー構造のフィクスチャ。
    - **期待値:** 返される候補リストの最初の要素が`<main>`タグを持つノードである。

#### `score_parent_and_children()`
- **目的:** 絞り込まれた候補（とその子孫）に対して、深さを考慮したスコアリングが正しく行われることを確認する。
- **Test Case 1: 深さによるスコア再計算**
    - **内容:** ジオメトリとテキストが同じで深さだけが違う親子のノードを作成し、子のスコアが親のスコアより高くなることを確認する。
    - **入力:** 同じ `rect` と `text` を持ち、`depth` が1と2の親子ノード。
    - **期待値:** 子ノードのスコア > 親ノードのスコア。

---

### 3.2. `core.py` (インテグレーションテスト)

**目的:** `content_extractor.core.extract_main_content` が、複数のモジュール（`make_tree`, `MainContentScorer`）と連携し、最も確からしいコンテンツブロックを特定するまでの絞り込みプロセス全体を検証する。

**Test Case 1: `extract_main_content` の絞り込みループ**
- **シナリオ:**
  初期スコアリングではメインコンテンツに見えないが、子要素を再評価するとよりスコアの高い子孫が見つかる、という状況をシミュレートする。
  具体的には、最初は広いコンテナ(`div#wrapper`)が高いスコアを持つが、その子孫である `article#main-article` が真の本文であり、再スコアリングによって最終的に選択されることを確認する。

- **テストフィクスチャ (Mock `make_tree` の返り値):**
  以下のような親子関係を持つDOMツリーを準備する。各ノードのスコアは `MainContentScorer` によって初期計算されると仮定する。

  ```
  body
  └── div#wrapper (score: 80)
      ├── nav (score: 10, is_valid=False)
      └── main
          └── article#main-article (score: 70)
              └── p (score: 95)
  ```

- **モック対象の動作:**
    1.  **`make_tree`:**
        - 上記のテストフィクスチャ（DOMツリー）を返すようにモックする。
    2.  **`MainContentScorer.find_candidates`:**
        - このツリーを評価し、`div#wrapper` と `article#main-article` を候補として返す。`div#wrapper` の方がスコアが高いとする。
    3.  **`rescore_main_content_with_children`:**
        - 呼び出されるたびに、渡されたノードの子孫を評価し、スコアを更新したリストを返すようにモックする。
        - 1回目の呼び出し（対象: `div#wrapper`）: `article#main-article` を含む子リストを返し、その中で `article#main-article` のスコアが更新されて `div#wrapper` より高くなるように設定する (例: 85)。
        - 2回目の呼び出し（対象: `article#main-article`）: `p` を含む子リストを返し、`p` のスコアがさらに高くなるように設定する (例: 95)。
        - 3回目の呼び出し（対象: `p`）: 子がいないため空リスト `[]` を返す。これによりループが終了する。

- **検証ステップ:**
    1.  `extract_main_content` を呼び出す。
    2.  内部で `MainContentScorer` が実行され、最初の候補として `div#wrapper` が選択されることを確認する。
    3.  `while` ループが開始される。
    4.  1回目の `rescore_main_content_with_children` 呼び出し後、次の最有力候補が `article#main-article` になることを確認する。
    5.  2回目の呼び出し後、次の最有力候補が `p` になることを確認する。
    6.  3回目の呼び出し後、空リストが返されループが終了することを確認する。
    7.  最終的に `extract_main_content` が `p` ノードを返すことをアサートする。

- **期待値:**
  最終的に返される `final_content` オブジェクトが、最も深い階層にある `p` タグのノードと一致する。

## 4. 新規テストの追加手順

新しいテストを追加する際は、以下の手順に従います。これにより、設計と実装の同期を保ちます。

1.  **設計書の更新:**
    本ドキュメント（`doc/test/test_design_content_extractor.md`）に、テスト対象の関数と具体的なテストケース（目的、入力、期待値）を追記します。

2.  **テストコードの実装:**
    対応するテストファイル（例: `test/test_scorer.py`）に、設計書に追記したテストケースを実装します。docstringのコメントで、設計書のどのテストケースに対応するかを明記します。

3.  **テストの実行と確認:**
    プロジェクトルートで `$env:PYTHONPATH = '.'; pytest` を実行し、追加したテストを含め、すべてのテストが成功することを確認します。

## 5. テストデータと実行

- **テストデータ:** `DOMTreeSt`と`BoundingBox`を`dataclass`からインポートし、テストケースごとにオブジェクトを生成して利用する。
- **実行方法:** プロジェクトのルートディレクトリで `$env:PYTHONPATH = '.'; pytest` を実行する。
