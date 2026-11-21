---
title: "content_extractor モジュール 詳細テスト設計書"
document_type: "test_plan_report"
document_role: "evidence"
ssot_scope: "test_evidence"
status: "approved"
version: "1.0"
created_at: "2026-11-20"
updated_at: "2026-11-21"
author: "xzyozi"
owner: "xzyozi"
purpose: "content_extractor モジュールのテスト方針とテストケースを定義するため"
related_documents:
  - "ドキュメントガバナンス（相対パス: ../README.md）"
  - "用語集（相対パス: ../../CONTEXT.md）"
---

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
- **Test Case 4: 範囲外の値やNoneの場合のエッジケース**
    - **内容:** 負の値、1.0を超える値、Noneが入力された場合。
    - **入力:** `occupancy_rate=-0.1`、`occupancy_rate=1.1`、`occupancy_rate=None`
    - **期待値:** スコアは0より大きく1.0以下になること。

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
- **Test Case 4: links属性がNoneの場合**
    - **内容:** `links`属性が`None`の場合でも、正しく処理されることを確認する。
    - **入力:** `DOMTreeSt(links=None)`
    - **期待値:** `0.1`
- **Test Case 5: links属性がリストでない場合**
    - **内容:** `links`属性がリスト以外の型の場合でも、正しく処理されることを確認する。
    - **入力:** `DOMTreeSt(links="not_a_list")`
    - **期待値:** `0.1`

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
- **Test Case 4: text属性がNoneの場合**
    - **内容:** `text`属性が`None`の場合でも、正しく処理されることを確認する。
    - **入力:** `DOMTreeSt(text=None)`
    - **期待値:** `0.0`
- **Test Case 5: text属性が文字列でない場合**
    - **内容:** `text`属性が文字列以外の型の場合でも、正しく処理されることを確認する。
    - **入力:** `DOMTreeSt(text=123)`
    - **期待値:** `0.0`

#### `calculate_depth_weight(current_depth)`
- **目的:** DOMの階層が深いほど高い重みが返されることを確認する。
- **Test Case 1: 浅い階層**
    - **入力:** `current_depth=0`
    - **期待値:** `1.0` (base_weight)
- **Test Case 2: 深い階層**
    - **入力:** `current_depth=5` (max_depth)
    - **期待値:** `4.0` (weight_factor)
- **Test Case 3: 中間的な深さ**
    - **内容:** 計算式に従って中間的な深さの重みが正しく計算されることを確認する。
    - **入力:** `current_depth=2.5` (max_depth=5, base_weight=1.0, weight_factor=4.0)
    - **期待値:** `2.0`
- **Test Case 4: 最大値を超える深さ**
    - **内容:** 深さが最大値を超えても、計算式に従って重みが正しく計算されることを確認する。
    - **入力:** `current_depth=6` (max_depth=5, base_weight=1.0, weight_factor=4.0)
    - **期待値:** `4.0 ** (6/5.0)`
- **Test Case 5: 負の深さ**
    - **内容:** 負の深さが0として扱われ、重みが正しく計算されることを確認する。
    - **入力:** `current_depth=-1`
    - **期待値:** `1.0` (0深度と同じ結果)

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
- **Test Case 4: IDに"main"を含む (大文字小文字無視)**
    - **内容:** ID属性に'main'（大文字小文字を区別しない）が含まれる場合。
    - **入力:** `DOMTreeSt(tag="div", attributes={"id": "has-MAIN-in-it"})`
    - **期待値:** `True`
- **Test Case 5: 属性なし**
    - **内容:** 属性を持たないタグの場合。
    - **入力:** `DOMTreeSt(tag="section")`
    - **期待値:** `False`
- **Test Case 6: 空の属性辞書**
    - **内容:** 属性辞書が空の場合。
    - **入力:** `DOMTreeSt(tag="div", attributes={})`
    - **期待値:** `False`
- **Test Case 7: IDに"main"を含む (混在ケース)**
    - **内容:** ID属性に'Main'（混在ケース）が含まれる場合。
    - **入力:** `DOMTreeSt(tag="div", attributes={"id": "my-Main-section"})`
    - **期待値:** `True`
- **Test Case 8: class属性に"main"を含む (idなし)**
    - **内容:** class属性に'main'が含まれるが、id属性には含まれない場合。
    - **入力:** `DOMTreeSt(tag="div", attributes={"class": "main-body", "id": "content"})`
    - **期待値:** `False`
- **Test Case 9: None入力やattributes/tagがNoneの場合のエッジケース**
    - **内容:** `node`自体が`None`、または`attributes`や`tag`が`None`の場合。
    - **入力:** `None`または`DOMTreeSt(tag=None, attributes={"id": "main"})`など
    - **期待値:** `AttributeError`発生、または`False`が返されること。

#### `is_valid_element(node)`
- **目的:** ノードがメインコンテンツ候補として有効か（除外タグでなく、小さすぎないか）を判定する。
- **Test Case 1: 有効なコンテナタグ**
    - **入力:** `DOMTreeSt(tag="div", rect=BoundingBox(width=100, height=100))`
    - **期待値:** `True`
- **Test Case 2: 無効なナビゲーションタグ**
    - **入力:** `DOMTreeSt(tag="nav", rect=BoundingBox(width=100, height=100))`
    - **期待値:** `False`
- **Test Case 3: 面積が小さすぎる**
    - **入力:** `DOMTreeSt(tag="div", rect=BoundingBox(width=0.2, height=0.2))`
    - **期待値:** `False`
- **Test Case 4: None入力やrect/tagがNoneの場合のエッジケース**
    - **内容:** `node`自体が`None`、または`rect`や`tag`が`None`の場合。
    - **入力:** `None`または`DOMTreeSt(tag="div", rect=None)`など
    - **期待値:** `AttributeError`発生、または`False`が返されること。

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

### 3.2. `make_tree.py` (ユニットテスト)

`make_tree.py`は、Playwrightの`Page`オブジェクトからDOMツリーを抽出し、`DOMTreeSt`オブジェクトの階層構造に変換する役割を担います。この処理は、コンテンツ抽出プロセスの基盤となるため、その正確性を保証することが重要です。

#### `make_tree(page, selector="body", wait_for_load=True, timeout=30000, debug=True)`
- **目的:** 指定されたセレクタからDOMツリーを正しく構築し、各ノードの情報を正確に抽出することを確認する。Playwrightの非同期操作とDOM解析の連携を検証する。
- **Test Case 1: 基本的なDOM構造の抽出**
    - **内容:** シンプルなHTMLコンテンツを持つページから、タグ名、ID、属性、テキスト、子要素が正確に抽出されることを確認する。
    - **入力:** モックされた`Page`オブジェクトと`ElementHandle`オブジェクト。`page.setContent()`で提供される単純なHTML文字列。
    - **期待値:** `DOMTreeSt`オブジェクトのツリー構造が、入力HTMLと一致すること。各ノードの`tag`、`id`、`attributes`、`text`、`children`が正しいこと。
- **Test Case 2: リンクの抽出**
    - **内容:** `<a>`タグとその`href`属性が正しく`links`リストに収集されることを確認する。
    - **入力:** `href`属性を持つ複数のリンクを含むHTML。
    - **期待値:** `DOMTreeSt`ノードの`links`属性に、抽出されたリンクのURLリストが（ソートされて）含まれていること。
- **Test Case 3: バウンディングボックスの抽出と要素のスキップ**
    - **内容:** `bounding_box()`が返す`rect`情報が正確に`BoundingBox`オブジェクトに変換されること、および`bounding_box()`が`None`を返す要素がツリーに含まれないことを確認する。
    - **入力:** 表示される要素と表示されない要素（`display: none`など）を含むHTML。
    - **期待値:** `DOMTreeSt`ノードの`rect`属性が正しいこと。`bounding_box()`が`None`を返した要素が結果のツリーに含まれていないこと。
- **Test Case 4: `selector`引数の機能**
    - **内容:** 特定のセレクタが指定された場合に、そのセレクタに合致する要素からのみツリーが構築されることを確認する。
    - **入力:** 複数の独立したセクションを持つHTMLと、特定のセクションを指すセレクタ。
    - **期待値:** `DOMTreeSt`のルートノードが指定されたセレクタに合致する要素であり、その子孫のみがツリーに含まれること。
- **Test Case 5: ルート要素が見つからない場合**
    - **内容:** 指定された`selector`に合致する要素がページ上に存在しない場合に、`None`が返されることを確認する。
    - **入力:** 存在しないセレクタ。
    - **期待値:** `make_tree`が`None`を返すこと。
- **Test Case 6: `wait_for_load`が`True`の場合**
    - **内容:** `wait_for_load`が`True`の場合に、`page.wait_for_load_state`が`networkidle`状態で呼び出されることを確認する。
    - **入力:** `wait_for_load=True`
    - **期待値:** `page.wait_for_load_state('networkidle', timeout=30000)`が呼び出されること。
- **Test Case 7: `wait_for_load`が`False`の場合**
    - **内容:** `wait_for_load`が`False`の場合に、`page.wait_for_load_state`が呼び出されないことを確認する。
    - **入力:** `wait_for_load=False`
    - **期待値:** `page.wait_for_load_state`が呼び出されないこと。

#### `make_css_selector(properties)` (ユニットテスト)
- **目的:** 要素のプロパティから安定したCSSセレクタが正しく生成されることを確認する。
- **Test Case 1: IDを持つ要素**
    - **内容:** `id`属性が提供されている場合、IDがセレクタとして優先されることを確認する。
    - **入力:** `{'tag': 'div', 'id': 'main-content', 'attributes': {'class': 'foo'}}`
    - **期待値:** `'div#main-content'`
- **Test Case 2: クラスのみを持つ要素**
    - **内容:** `id`がなく`class`属性がある場合、クラス名がセレクタとして使用されることを確認する。
    - **入力:** `{'tag': 'p', 'attributes': {'class': 'text-center article-body'}}`
    - **期待値:** `'p.text-center.article-body'`
- **Test Case 3: IDもクラスも持たない要素**
    - **内容:** `id`も`class`もない場合、タグ名のみがセレクタとして使用されることを確認する。
    - **入力:** `{'tag': 'span'}`
    - **期待値:** `'span'`
- **Test Case 4: 属性が複雑な要素**
    - **内容:** `class`属性に複数のクラスが含まれる場合や、`id`と`class`が混在する場合でも正しくセレクタが生成されることを確認する。
    - **入力:** `{'tag': 'a', 'id': 'unique-link', 'attributes': {'class': 'button primary'}}`
    - **期待値:** `'a#unique-link'`
- **Test Case 5: 空のproperties**
    - **内容:** 必須プロパティが欠けている場合の挙動。
    - **入力:** `{'tag': ''}` または `{}`
    - **期待値:** `''` または適切なデフォルト値。
- **Test Case 6: タグが欠けている場合**
    - **内容:** `tag`属性が空の場合に、IDやクラスのみでセレクタが生成されることを確認する。
    - **入力:** `{'tag': '', 'id': 'my-id', 'attributes': {'class': 'my-class'}}`
    - **期待値:** `'#my-id'`
- **Test Case 7: タグもIDも空の場合**
    - **内容:** `tag`も`id`も空の場合。
    - **入力:** `{'tag': '', 'id': '', 'attributes': {}}`
    - **期待値:** `''`
- **Test Case 8: class属性に複数のスペースを含む場合**
    - **内容:** class属性値の間に複数のスペースが含まれていても、正しく処理されることを確認する。
    - **入力:** `{'tag': 'div', 'id': '', 'attributes': {'class': '  class1   class2  '}}`
    - **期待値:** `'div.class1.class2'`
- **Test Case 9: class属性がない場合**
    - **内容:** class属性がない場合でも、IDが優先され正しくセレクタが生成されることを確認する。
    - **入力:** `{'tag': 'div', 'id': 'my-id', 'attributes': {'style': 'color: red;'}}`
    - **期待値:** `'div#my-id'`

#### `escape_css_identifier(value)`
- **目的:** CSSの識別子（ID・クラス名）をブラウザの `CSS.escape()` と同じ規則でエスケープし、数字始まりのIDやTailwindCSSの記号を含むクラス名を有効なセレクタとして扱えることを確認する。
- **Test Case 1: 英数字・ハイフン・アンダースコア**
    - **内容:** エスケープ不要な基本識別子がそのまま返されることを確認する。
    - **入力:** `'main'`、 `'_x'`
    - **期待値:** `'main'`、 `'_x'`
- **Test Case 2: TailwindCSS等の記号（コロン・スラッシュ・ドット・空白）**
    - **内容:** `:`, `/`, `.`, 空白を含むクラス名がバックスラッシュでエスケープされることを確認する。
    - **入力:** `'md:px-4'`、 `'w-1/2'`、 `'a.b'`、 `'a b'`
    - **期待値:** `'md\\:px-4'`、 `'w-1\\/2'`、 `'a\\.b'`、 `'a\\ b'`
- **Test Case 3: 先頭が数字、または `-` の2文字目が数字、および `-` 単独**
    - **内容:** CSS識別子として無効にならないよう、数字が16進エスケープ（後ろに空白）され、`-` 単独が `\\-` になることを確認する。
    - **入力:** `'1abc'`、 `'-1abc'`、 `'-'`
    - **期待値:** `'\\31 abc'`、 `'-\\31 abc'`、 `'\\-'`
- **Test Case 4: 非ASCII文字**
    - **内容:** 日本語などの非ASCII文字がそのまま保持されることを確認する。
    - **入力:** `'日本語'`
    - **期待値:** `'日本語'`
- **Test Case 5: `make_css_selector` との連携**
    - **内容:** 数字始まりのIDやTailwindCSSクラス名を含む要素プロパティから、エスケープ済みの有効なセレクタが生成されることを確認する。
    - **入力:** `{'tag': 'div', 'id': '1abc', 'attributes': {}}`、 `{'tag': 'div', 'id': '', 'attributes': {'class': 'w-1/2 md:px-4'}}`
    - **期待値:** `'div#\\31 abc'`、 `'div.w-1\\/2.md\\:px-4'`

---

### 3.3. `config.py` (ユニットテスト)

`config.py`は、モジュールで使用される設定ファイルを読み込む役割を担います。

#### `_load_json_config(filename, default_config)`
- **目的:** JSON設定ファイルを安全に読み込み、ファイルが存在しない場合や内容が不正な場合には、指定されたデフォルト設定を返すことを確認する。
- **Test Case 1: 設定ファイルの読み込み成功**
    - **内容:** 有効なJSON設定ファイルが正しく読み込まれ、その内容が返されることを確認する。
    - **入力:** `{"key": "custom_value"}` を含むJSONファイル。
    - **期待値:** `{"key": "custom_value"}` が返されること。
- **Test Case 2: 設定ファイルが存在しない**
    - **内容:** 設定ファイルが見つからない場合に、`FileNotFoundError`が捕捉され、デフォルト設定が返されることを確認する。
    - **入力:** 存在しないファイルパス。
    - **期待値:** デフォルト設定が返されること。
- **Test Case 3: 不正なJSON形式**
    - **内容:** 設定ファイルの内容が不正なJSON形式である場合に、`JSONDecodeError`が捕捉され、デフォルト設定が返されることを確認する。
    - **入力:** `{ 'key': 'invalid_json' }` のような不正な形式のJSONファイル。
    - **期待値:** デフォルト設定が返されること。

---

### 3.4. `dom_utils.py` (ユニットテスト)

`dom_utils.py`は、`DOMTreeSt`オブジェクトを操作するためのユーティリティ関数を提供します。これらの関数はコンテンツ抽出ロジックの重要な一部であるため、その正確性と堅牢性を保証するためにテストが必要です。

#### `flatten_dom_tree(node)`
- **目的:** DOMツリーを構成するすべてのノードを、ルートから子孫まで順序付けられたフラットなリストとして正しく返すことを確認する。
- **Test Case 1: 単一ノードのツリー**
    - **内容:** 子を持たない`DOMTreeSt`ノードが入力された場合、そのノードのみを含むリストが返されることを確認する。
    - **入力:** `DOMTreeSt(tag='div')`
    - **期待値:** `[DOMTreeSt(tag='div')]`
- **Test Case 2: シンプルな親子関係**
    - **内容:** 親ノードと直接の子ノードがいくつかある場合に、正しくフラット化されることを確認する。
    - **入力:** `DOMTreeSt(tag='body', children=[DOMTreeSt(tag='div'), DOMTreeSt(tag='p')])`
    - **期待値:** `[body_node, div_node, p_node]` (順序はdfs順)
- **Test Case 3: 複数階層のツリー**
    - **内容:** 複数レベルでネストされたDOMツリーが、期待される順序（深さ優先検索順）でフラット化されることを確認する。
    - **入力:** `body -> div1 -> p1, div2 -> p2` のような複雑な構造。
    - **期待値:** `[body, div1, p1, div2, p2]`
- **Test Case 4: 空の`children`リストを持つノード**
    - **内容:** `children`リストが空のノードが入力された場合。
    - **入力:** `DOMTreeSt(tag='span', children=[])`
    - **期待値:** `[DOMTreeSt(tag='span')]`

#### `rescore_main_content_with_children(main_content)`
- **目的:** 指定されたメインコンテンツ候補とその子孫ノードが、`MainContentScorer`を用いて正しく再スコアリングされ、スコアの高い順にソートされたリストとして返されることを確認する。
- **Test Case 1: 基本的な再スコアリングとソート**
    - **内容:** ダミーの`DOMTreeSt`構造とモックされた`MainContentScorer`を使用して、再スコアリングプロセスと結果のソート順が正しいことを確認する。
    - **入力:** スコアが異なるいくつかのノードを含む`DOMTreeSt`サブツリー。`MainContentScorer.score_parent_and_children`のモックは、期待されるスコアのリストを返すように設定される。
    - **期待値:** 返される`DOMTreeSt`のリストが、降順にスコア付けされていること。
- **Test Case 2: 無効な入力タイプ**
    - **内容:** `main_content`が`DOMTreeSt`型ではない場合に、`TypeError`が適切に発生することを確認する。
    - **入力:** `None`や`str`などの無効な型の`main_content`。
    - **期待値:** `TypeError`が発生すること。
- **Test Case 3: 子ノードがない場合**
    - **内容:** `main_content`ノードに子がない場合でも、正しく処理され、自身のみを含む（または空の）ソート済みリストが返されることを確認する。
    - **入力:** 子ノードがない`DOMTreeSt`。
    - **期待値:** `main_content`ノード自体を含む（または`MainContentScorer`の動作によっては空の）リストが返されること。
- **Test Case 4: `MainContentScorer`が空リストを返す場合**
    - **内容:** `MainContentScorer.score_parent_and_children`が空リストを返した場合。
    - **入力:** `MainContentScorer`が空リストを返すようにモックされた`main_content`。
    - **期待値:** 空のリスト`[]`が返されること。

---

### 3.5. `playwright_helpers.py` (ユニットテスト)

`playwright_helpers.py`モジュールは、Playwrightを使用したブラウザ自動化、`robots.txt`の取得と解析、スクリーンショットの保存など、多様なユーティリティ機能を提供します。これらの機能は外部システム（ブラウザ、ネットワーク、ファイルシステム）との連携が多いため、広範なモックと非同期テストが必要です。

#### `setup_page(url, browser)`
- **目的:** Playwrightの`Page`オブジェクトを正しく初期化し、指定されたURLへ遷移し、ページの読み込み状態を適切に待機することを確認する。
- **Test Case 1: 正常なページセットアップ**
    - **内容:** `page.goto`、`page.wait_for_selector`、`page.wait_for_load_state`が期待通りに呼び出され、`Page`オブジェクトが返されることを確認する。
    - **入力:** 有効なURLとモックされた`Browser`オブジェクト。
    - **期待値:** `Page`オブジェクトが正常に返され、関連するPlaywrightメソッドが正しい引数で呼び出されること。
- **Test Case 2: `goto`または`wait_for_selector`でのタイムアウト**
    - **内容:** `page.goto`または`page.wait_for_selector`が`PlaywrightTimeoutError`を発生させた場合に、エラーが適切にログに記録され、作成済みリソース（`Page`・`BrowserContext`）を解放して`None`が返されることを確認する。
    - **入力:** タイムアウトを発生させるようにモックされたPlaywrightメソッド。
    - **期待値:** エラーがログに記録され、`page.close`と`context.close`が呼ばれたうえで、関数が`None`を返すこと。
- **Test Case 3: `wait_for_load_state`でのタイムアウト**
    - **内容:** `page.wait_for_load_state`が`PlaywrightTimeoutError`を発生させた場合に、警告がログに記録されるが、処理は続行され`Page`オブジェクトが返されることを確認する。
    - **入力:** `wait_for_load_state`がタイムアウトするようモックされたPlaywrightメソッド。
    - **期待値:** 警告がログに記録され、`Page`オブジェクトが返されること。
- **Test Case 4: `PlaywrightError` の発生**
    - **内容:** `PlaywrightTimeoutError`以外の`PlaywrightError`（`new_page`・`goto`等の失敗）が発生した場合に、エラーがログに記録され、作成済みの`Page`および`BrowserContext`を解放したうえで`None`が返されることを確認する。また、`page.close`が`PlaywrightError`を出した場合でも`context.close`が呼ばれることを確認する（#47・#63）。
    - **入力:** `PlaywrightError`を発生させるようにモックされたPlaywrightメソッド（`page.goto`、`context.new_page`、`page.close`）。
    - **期待値:** エラー（`page.close`失敗時は警告）がログに記録され、作成済みの`Page`・`BrowserContext`が解放されたうえで、関数が`None`を返すこと。
- **Test Case 5: 予期せぬ例外（`PlaywrightError`以外）の再送出**
    - **内容:** `RuntimeError`等のPlaywright関連以外の予期せぬ例外が発生した場合に、`logger.exception`でログに記録し、作成済みの`Page`および`BrowserContext`を解放したうえで例外を握りつぶさず再送出することを確認する（#47・#63）。
    - **入力:** `RuntimeError`等の非Playwright例外を発生させるようにモックされたメソッド。
    - **期待値:** `logger.exception`が呼ばれ、作成済みの`Page`・`BrowserContext`が解放されたうえで、発生した例外がそのまま再送出されること。

#### `close_page(page)`

- **目的:** `setup_page` が作成した `Page` と、その `BrowserContext` の両方を閉じ、例外発生時もログ記録のみで後続処理を止めないことを確認する。

- **Test Case 1: ページとコンテキストの正常クローズ**

    - **内容:** ページを閉じた後、紐づくブラウザコンテキストも閉じられ、コンテキストのリークを防ぐことを確認する。

    - **入力:** モックされた `Page`（`page.context` にモック `BrowserContext` を設定）。

    - **期待値:** `page.close` と `page.context.close` がそれぞれ1回ずつ await されること。

- **Test Case 2: クローズ失敗時の例外抑制**

    - **内容:** `page.close` 等で例外が発生した場合でも例外を送出せず、警告ログのみを記録することを確認する。

    - **入力:** `page.close` が例外を送出するようにモックされた `Page`。

    - **期待値:** 例外を送出せず正常終了し、`logger.warning` が1回呼ばれること。

#### `ensure_unique_selector(page, selector, rect)`

- **目的:** セレクタがページ内で1件のみにヒットする場合はそのまま返し、複数件にヒットする場合は位置（`rect`）が一致する要素の `nth-of-type` 絶対パスへ置き換えること、および異常系では元のセレクタを返すことを確認する。

- **Test Case 1: ヒット件数が1件の場合**

    - **内容:** ページ内で1件だけにヒットするセレクタは変更せずにそのまま返す。

    - **入力:** `selector="div.card"`、`page.evaluate` の戻り値が `{"count": 1, "path": "..."}`。

    - **期待値:** `"div.card"` が返されること。

- **Test Case 2: 複数件ヒットし位置が一致した場合**

    - **内容:** 同じセレクタが複数要素にヒットする場合、JavaScript評価で特定した `nth-of-type` パスに置き換える。

    - **入力:** `selector="div.card"`、`page.evaluate` の戻り値が `{"count": 3, "path": "html > body > div:nth-of-type(2)"}`。

    - **期待値:** `"html > body > div:nth-of-type(2)"` が返されること。

- **Test Case 3: 複数件ヒットしたが位置が一致しない場合**

    - **内容:** `path` が `None` の場合は元のセレクタを保持する。

    - **入力:** `page.evaluate` の戻り値が `{"count": 3, "path": None}`。

    - **期待値:** `"div.card"` が返されること。

- **Test Case 4: `page.evaluate` が例外を送出する場合**

    - **内容:** JavaScriptの評価に失敗しても例外を送出せず、元のセレクタを返す。

    - **入力:** `page.evaluate` が例外を送出するようにモックされた `Page`。

    - **期待値:** `"div.card"` が返されること。

- **Test Case 5: `page.evaluate` が予期しない型を返す場合**

    - **内容:** 戻り値が辞書でない場合は元のセレクタを返す。

    - **入力:** `page.evaluate` の戻り値が `"unexpected"`。

    - **期待値:** `"div.card"` が返されること。

- **Test Case 6: 空のセレクタが渡された場合**

    - **内容:** 空文字列の場合は `page.evaluate` を実行せずそのまま返す。

    - **入力:** `selector=""`。

    - **期待値:** `""` が返され、`page.evaluate` が呼ばれないこと。

#### `adjust_page_view(page)`

- **目的:** ページのコンテンツに基づいてビューポートのサイズが正しく計算され、設定されること、およびページが最下部までスクロールされることを確認する。

- **Test Case 1: 正しいビューポートサイズ設定とスクロール**

    - **内容:** `page.evaluate`が正しいJavaScriptコードを実行してページの寸法を取得し、`page.set_viewport_size`がこれらの寸法で呼び出され、`window.scrollTo`が呼び出されることを確認する。

    - **入力:** モックされた`Page`オブジェクト。

    - **期待値:** `page.evaluate`と`page.set_viewport_size`、`page.wait_for_timeout`が正しい引数で呼び出され、計算された寸法が返されること（`height`が`page.evaluate`から返される`height`値と一致すること）。



#### `fetch_robots_txt(url)`

- **目的:** 指定されたURLから`robots.txt`の内容を非同期で取得できること、およびネットワークエラーや無効なレスポンスを適切に処理できることを確認する。

- **Test Case 1: 正常な`robots.txt`の取得**

    - **内容:** `aiohttp.ClientSession`を使用して`robots.txt`が正常にフェッチされ、内容が文字列として返されることを確認する。

    - **入力:** 有効なURLとモックされた`aiohttp`リクエスト。

    - **期待値:** `robots.txt`の内容が文字列として返されること。

- **Test Case 2: `robots.txt`が見つからない (404)**

    - **内容:** `robots.txt`のURLが404 Not Foundを返した場合に、`None`が返されることを確認する。

    - **入力:** 404を返すようにモックされた`aiohttp`リクエスト。

    - **期待値:** `None`が返されること。

- **Test Case 3: ネットワークエラー**

    - **内容:** ネットワーク接続の問題などで`aiohttp`が例外を発生させた場合に、`None`が返されることを確認する。

    - **入力:** 例外を発生させるようにモックされた`aiohttp`リクエスト。

    - **期待値:** `None`が返されること。



#### `is_scraping_allowed(robots_txt, target_path)`

- **目的:** `robots.txt`の内容を正確に解析し、指定されたパスのスクレイピングが許可されているか否かを正しく判断できることを確認する。

- **Test Case 1: 許可されているパス**

    - **内容:** `User-agent: * Disallow: /admin` のような`robots.txt`において、`/allowed/path`が許可されることを確認する。

    - **入力:** `robots.txt`の内容と、許可されるパス。

    - **期待値:** `True`が返されること。

- **Test Case 2: 禁止されているパス**

    - **内容:** `User-agent: * Disallow: /private` のような`robots.txt`において、`/private/data`が禁止されることを確認する。

    - **入力:** `robots.txt`の内容と、禁止されるパス。

    - **期待値:** `False`が返されること。

- **Test Case 3: `robots.txt`が存在しない（空の文字列）**

    - **内容:** `robots_txt`が空の場合に、すべてのパスが許可されることを確認する。

    - **入力:** 空文字列と任意のパス。

    - **期待値:** `True`が返されること。

- **Test Case 4: コメント行と空行の処理**

    - **内容:** `robots.txt`内のコメント行や空行が正しく無視されることを確認する。

    - **入力:** コメントと空行を含む`robots.txt`。

    - **期待値:** 正しい許可/不許可の判断がなされること。

#### `is_url_allowed(url)`

- **目的:** `robots.txt` に基づいて対象URLへのアクセス可否を判定し、オリジン単位で取得結果（取得失敗を含む）をキャッシュすることを確認する。

- **Test Case 1: `robots.txt` による許可・禁止判定**

    - **内容:** `Disallow: /private` を含む `robots.txt` に対して、禁止パスは `False`、許可パスは `True` を返すことを確認する。

    - **入力:** `fetch_robots_txt` が `"User-agent: *\nDisallow: /private"` を返すようにモックし、`"http://example.com/private/data"` と `"http://example.com/public/page"` を渡す。

    - **期待値:** それぞれ `False` と `True` が返されること。

- **Test Case 2: オリジンごとのキャッシュ共有**

    - **内容:** 同一オリジンの複数URLを判定する際、`fetch_robots_txt` がオリジンごとに1回だけ呼ばれることを確認する。

    - **入力:** `"http://example.com/a"`, `"http://example.com/b"`, `"http://other.example.org/a"`。

    - **期待値:** `fetch_robots_txt` の呼び出し回数が2回（オリジン数分）であること。

- **Test Case 3: `robots.txt` 取得失敗時の許可とキャッシュ**

    - **内容:** `fetch_robots_txt` が `None` を返した場合は許可（`True`）とし、取得失敗もキャッシュして同一オリジンへ再取得しないことを確認する。

    - **入力:** `fetch_robots_txt` が `None` を返す状態で `"http://example.com/a"` と `"http://example.com/b"` を連続判定。

    - **期待値:** いずれも `True` が返され、`fetch_robots_txt` の呼び出し回数が1回であること。

- **Test Case 4: 解析できないURL**

    - **内容:** スキームやホストを含まない無効なURLは `fetch_robots_txt` を呼ばずに `True`（許可）を返すことを確認する。

    - **入力:** `"invalid-url"`。

    - **期待値:** `True` が返され、`fetch_robots_txt` が呼ばれないこと。



#### `save_screenshot(browser, url_list, save_dir="temp", width=500, height=None)`

- **目的:** 複数のURLに対してスクリーンショットを撮影し、指定されたディレクトリに保存、リサイズできること、およびエラーやリトライを適切に処理できることを確認する。

- **Test Case 1: 正常なスクリーンショットの保存とリサイズ**

    - **内容:** 有効なURLリストに対して、各URLのスクリーンショットが撮影され、指定された幅にリサイズされ、ファイルとして保存されることを確認する。

    - **入力:** 有効なURLリストとモックされたPlaywright、`PIL.Image`、`os`モジュール。

    - **期待値:** 各URLに対して有効なファイルパスがリストとして返され、ファイルシステム操作と画像処理が正しく行われること。

- **Test Case 2: 無効なURLのスキップ**

    - **内容:** `url_list`内に無効なURLが含まれている場合に、そのURLがスキップされ、対応するリストエントリが`None`になることを確認する。

    - **入力:** 有効なURLと無効なURLの混合リスト。

    - **期待値:** 無効なURLに対して`None`が返されること。

- **Test Case 3: リトライメカニズム**

    - **内容:** `PlaywrightTimeoutError`などの一時的なエラーが発生した場合に、指定された回数だけリトライが実行され、最終的に成功するか、最大試行回数を超えて失敗することを確認する。

    - **入力:** 最初の数回はエラーを発生させ、その後成功するようにモックされたPlaywright操作。

    - **期待値:** リトライロジックが正しく実行され、最終結果（成功したパスまたは`None`）が返されること。

- **Test Case 4: 最大リトライ回数を超えた失敗**

    - **内容:** 常にエラーを発生させるようにモックされたPlaywright操作に対して、最大リトライ回数を超えた後に`None`が返されることを確認する。

    - **入力:** 常にエラーを発生させるPlaywright操作。

    - **期待値:** `None`が返されること。

- **Test Case 5: 画像リサイズ時のアスペクト比保持**

    - **内容:** `height`が指定されない場合に、`width`に基づいて元画像の正確なアスペクト比を保ってリサイズされることを確認する。

    - **入力:** 元の画像サイズと`width`。

    - **期待値:** `PIL.Image.Image.resize`が正しい`width`と計算された`height`で呼び出されること。

- **Test Case 6: ディレクトリの作成**

    - **内容:** スクリーンショット保存ディレクトリが存在しない場合に、`os.makedirs`が正しく呼び出されることを確認する。

    - **入力:** 新規の保存ディレクトリパス。

    - **期待値:** `os.makedirs(save_dir, exist_ok=True)`が呼び出されること。



#### `generate_filename(url)`

- **目的:** URLから一意でファイルシステムに適したファイル名を正しく生成できることを確認する。

- **Test Case 1: 基本的なURLからの生成**

    - **内容:** シンプルなURLからドメイン、パスの最後の部分、ハッシュを含むファイル名が生成されることを確認する。

    - **入力:** `https://example.com/some/path/page.html`

    - **期待値:** `'example_com_page_html_[hash].png'`のような形式の文字列。

- **Test Case 2: クエリパラメータを含むURL**

    - **内容:** クエリパラメータがファイル名生成に影響しないことを確認する。

    - **入力:** `https://example.com/page?param=value`

    - **期待値:** `'example_com_page_[hash].png'`のような形式の文字列。

- **Test Case 3: 特殊文字を含むURL**

    - **内容:** URL内の特殊文字（ファイルシステムで許可されないもの）が適切に処理され、有効なファイル名が生成されることを確認する。

    - **入力:** `https://example.com/path/with spaces/file!.html`

    - **期待値:** 有効なファイル名が生成されること。

- **Test Case 4: ルートURL**

    - **内容:** ドメインのみのURLが正しくファイル名に変換されることを確認する。

    - **入力:** `https://example.com`

    - **期待値:** `'example_com_index_[hash].png'`のような形式の文字列。



---



### 3.8. `web_type_chk.py` (ユニットテスト)



`web_type_chk.py`は、URLとDOM情報から、ページがページネーション（複数ページにまたがる一覧）の一部であるかを判定し、次のページ（最新ページ）のURLを特定する役割を担います。



#### `PageMonitor.determine_watch_page()`

- **目的:** 現在のURLとページ内のリンクから、次に巡回すべき最新ページのURLを正しく特定できることを確認する。

- **Test Case 1: 標準的なページネーション**

    - **内容:** `page-` 形式のURLで、より新しいページ番号のリンクが存在する場合。

    - **入力:** `base_url=".../page-1"`, `links=[".../page-2", ".../page-10"]`

    - **期待値:** `".../page-10"`

- **Test Case 2: 既に最新ページにいる場合**

    - **内容:** `base_url`のページ番号が、リンク内の最大ページ番号と同じか、それより大きい場合。

    - **入力:** `base_url=".../page-10"`, `links=[".../page-8", ".../page-9"]`

    - **期待値:** `None`

- **Test Case 3: 相対パスのリンク**

    - **内容:** リンクが相対パスで指定されている場合に、`base_url`を基準に正しく絶対URLに解決できることを確認する。

    - **入力:** `base_url="http://example.com/articles/page/3"`, `links=["/articles/page/5"]`

    - **期待値:** `"http://example.com/articles/page/5"`

- **Test Case 4: ベースURLがページネーション形式でない場合**

    - **内容:** `base_url`自体がページネーションのパターンに一致しない場合、何も返さないことを確認する。

    - **入力:** `base_url=".../article.html"`, `links=[".../page-2"]`

    - **期待値:** `None`



#### `WebTypeCHK.webtype_chk()`

- **目的:** `PageMonitor`と連携し、ページの種別（`page_changer`または`plane`）を判定し、次のページのURLを正しく設定できることを確認する。

- **Test Case 1: 次ページが存在する場合**

    - **内容:** `determine_watch_page`が新しいURLを返す場合。

    - **入力:** `base_url=".../page/3"`, `links=[".../page/5"]`

    - **期待値:** `webtype`が`"page_changer"`、`next_url`が`".../page/5"`となること。

- **Test Case 2: 最新ページだが、URL自体はページャー形式**

    - **内容:** `determine_watch_page`が`None`を返すものの、`base_url`自体がページネーションパターンに一致する場合。

    - **入力:** `base_url=".../page-10"`, `links=[".../page-9"]`

    - **期待値:** `webtype`が`"page_changer"`、`next_url`が`None`となること。

- **Test Case 3: ページネーションでない場合**

    - **内容:** `base_url`もリンクもページネーションパターンに一致しない場合。

    - **入力:** `base_url=".../article.html"`, `links=[]`

    - **期待値:** `webtype`が`"plane"`、`next_url`が`None`となること。

- **Test Case 4: ページネーションでなく、リンクも存在しない場合**

    - **内容:** `base_url`がページネーションパターンに一致せず、ページ内にリンクも存在しない場合。

    - **入力:** `base_url=".../article.html"`, `links=[]` (`node_data_no_links`使用)

    - **期待値:** `webtype`が`"plane"`、`next_url`が`None`となること。

    

    

    

    ---

    

    

    

    ### 3.9. `_escape_css_selector_colons` (ユニットテスト)

    

    - **目的:** CSSセレクタ内のクラス名に含まれるコロンが正しくエスケープされることを確認する。PlaywrightがTailwindCSSなどのクラス名を正しく解釈できるようにする。

    

    - **Test Case 1: 標準的なTailwindCSSクラス**

        - **内容:** `md:px-12` のような形式のクラス名が正しくエスケープされることを確認する。

        - **入力:** `'div.px-6.py-12.md:px-12.md:py-16'`

        - **期待値:** `'div.px-6.py-12.md\\:px-12.md\\:py-16'`

    

    - **Test Case 2: 複数のコロンを含むクラス名**

        - **内容:** `sm:text-lg:hover` のような複数のコロンを含むクラス名が正しくエスケープされることを確認する。

        - **入力:** `'span.sm:text-lg:hover'`

        - **期待値:** `'span.sm\\:text-lg\\:hover'`

    

    - **Test Case 3: コロンを含まないセレクタ**

        - **内容:** コロンを含まない通常のCSSセレクタが変更されないことを確認する。

        - **入力:** `'div.container'`

        - **期待値:** `'div.container'`

    

    - **Test Case 4: 擬似クラス（コロンがエスケープ不要な場合）**

        - **内容:** `:hover` や `:nth-child(n)` のような擬似クラスのコロンがエスケープされないことを確認する。

        - **入力:** `'a:hover'`

        - **期待値:** `'a:hover'`

        - **入力:** `'p:nth-child(2n+1)'`

        - **期待値:** `'p:nth-child(2n+1)'`

    

    - **Test Case 5: 既にエスケープされているコロン**

        - **内容:** 既にエスケープされているコロンが二重にエスケープされないことを確認する。

        - **入力:** `'div.md\\:px-12'`

        - **期待値:** `'div.md\\:px-12'`

    

    - **Test Case 6: 複雑なセレクタの組み合わせ**

        - **内容:** ID、クラス、擬似クラスなどが混在する複雑なセレクタで正しくエスケープされることを確認する。

        - **入力:** `'#header > div.md:flex-col:first-child a:hover'`

        - **期待値:** `'#header > div.md\\:flex-col:first-child a:hover'`

    



### 3.7. `relevance_scorer.py` (ユニットテスト)



`relevance_scorer.py`は、検索クエリと検索結果アイテムの関連性を評価し、総合的な品質スコア（SQS）を算出します。



#### `_calculate_jaccard(text1, text2)`

- **目的:** 2つのテキスト間のジャカード類似度を正しく計算できることを確認する。

- **Test Case 1: 通常の計算**

    - **内容:** 共通の単語とユニークな単語を持つ2つの文。

    - **入力:** `text1="hello world from python"`, `text2="hello python universe"`

    - **期待値:** `0.4` (共通2語 / 全体5語)

- **Test Case 2: 共通語なし**

    - **内容:** 共通の単語が一つもない場合。

    - **入力:** `text1="a b c"`, `text2="d e f"`

    - **期待値:** `0.0`

- **Test Case 3: 空文字列**

    - **内容:** 両方の文字列が空の場合。

    - **入力:** `text1=""`, `text2=""`

    - **期待値:** `0.0`



#### `score_relevance(query, items)`

- **目的:** Jaccard、TF-IDF、Semantic-Transformerの3つのスコアを組み合わせたハイブリッド関連性スコアを正しく計算できることを確認する。

- **Test Case 1: ハイブリッドスコアの計算**

    - **内容:** `_calculate_jaccard`, `cosine_similarity`, `cos_sim` をモックし、各スコアに重みを掛けた合計が期待通りになることを確認する。

    - **入力:** クエリ文字列と`DOMTreeSt`アイテムのリスト。

    - **期待値:** 各アイテムの`relevance_score`が、重み付けされたスコアの合計値と一致すること。

- **Test Case 2: 空のアイテムリスト**

    - **内容:** スコアリング対象のアイテムがない場合。

    - **入力:** `items=[]`

    - **期待値:** 空のリスト `[]` が返されること。



#### `calculate_sqs(result_count, avg_relevance, relevance_variance, max_relevance)`

- **目的:** 検索結果の統計情報から、品質スコア（SQS）と品質カテゴリを正しく計算できることを確認する。

- **Test Case 1: 「Valid」カテゴリの計算**

    - **内容:** 高品質な検索結果を示す入力値。

    - **入力:** `result_count=10`, `avg_relevance=0.8`, `relevance_variance=0.1`, `max_relevance=0.9`

    - **期待値:** SQSスコアが「Valid」の閾値（例: 60）以上になり、カテゴリが "Valid" となること。

- **Test Case 2: 「Low Quality」カテゴリの計算**

    - **内容:** 低品質な検索結果を示す入力値。

    - **入力:** `result_count=3`, `avg_relevance=0.4`, `relevance_variance=0.3`, `max_relevance=0.5`

    - **期待値:** SQSスコアが「Low Quality」の範囲内（例: 20-60）になり、カテゴリが "Low Quality" となること。

- **Test Case 3: 「Invalid/Empty」カテゴリの計算**

    - **内容:** 非常に低い品質の検索結果を示す入力値。

    - **入力:** `result_count=1`, `avg_relevance=0.1`, `relevance_variance=0.5`, `max_relevance=0.2`

    - **期待値:** SQSスコアが「Invalid/Empty」の閾値（例: 20）未満になり、カテゴリが "Invalid/Empty" となること。

- **Test Case 4: 結果ゼロの場合**

    - **内容:** 検索結果が0件の場合。

    - **入力:** `result_count=0`

    - **期待値:** SQSスコアが `0`、カテゴリが "Invalid/Empty" となること。

- **Test Case 5: SQSスコアがマイナスになる場合**

    - **内容:** 計算結果が負になるような入力値の場合、スコアが0に丸められることを確認する。

    - **入力:** `result_count=1`, `avg_relevance=0.1`, `relevance_variance=1.0`, `max_relevance=0.1`

    - **期待値:** SQSスコアが `0` となること。



---



### 3.6. `quality_evaluator.py` (ユニットテスト)



`quality_evaluator.py`は、抽出されたコンテンツが「検索結果なしかどうか」を判定し、検索結果の品質を定量化する役割を担います。



#### `is_no_results_page(page, dom_tree)`

- **目的:** ページが「結果なし」の状態であるかを、キーワード、CSSセレクタ、期待されるコンテナの有無から正しく判定できることを確認する。

- **Test Case 1: キーワードによる判定**

    - **内容:** DOMツリーのテキストに「結果なし」を示すキーワードが含まれている場合。

    - **入力:** `dom_tree`に "no results found" を含むテキスト、モックされた`page`オブジェクト。

    - **期待値:** `True`が返されること。

- **Test Case 2: 「結果なし」セレクタによる判定**

    - **内容:** ページ内に「結果なし」を示すCSSセレクタを持つ要素が存在する場合。

    - **入力:** `page.evaluate`が`True`を返すようにモックされた`page`オブジェクト。

    - **期待値:** `True`が返されること。

- **Test Case 3: 期待される結果コンテナが存在することによる判定**

    - **内容:** ページ内に期待される結果コンテナのセレクタが存在する場合、「結果なし」ではないと判定されること。

    - **入力:** `page.evaluate`が1回目の呼び出しで`False`（「結果なし」セレクタなし）、2回目の呼び出しで`True`（期待セレクタあり）を返すようにモック。

    - **期待値:** `False`が返されること。

- **Test Case 4: キーワードもセレクタも存在しない場合**

    - **内容:** 「結果なし」の兆候がなく、かつ期待される結果コンテナも見つからない場合、「結果なし」と判定されること。

    - **入力:** `page.evaluate`が常に`False`を返すようにモック。

    - **期待値:** `True`が返されること。



#### `_find_result_container(main_content_node)`

- **目的:** メインコンテンツノード内から、最も繰り返し構造を持つ子要素のコンテナを正しく特定できることを確認する。

- **Test Case 1: 繰り返しクラスを持つコンテナの特定**

    - **内容:** 子要素に同じクラス名が複数回出現するコンテナを特定する。

    - **入力:** `class="result-item"` を持つ子要素が複数含まれる`DOMTreeSt`ノード。

    - **期待値:** `class="results-list"` を持つ親ノードが返されること。

- **Test Case 2: 明確なコンテナがない場合**

    - **内容:** 子要素に繰り返し構造が見られない場合。

    - **入力:** 子要素がすべて異なるクラス名を持つ`DOMTreeSt`ノード。

    - **期待値:** `None`が返されること。



#### `quantify_search_results(main_content_node)`

- **目的:** 特定された結果コンテナから、有効な検索結果アイテムを抽出し、その数をカウントできることを確認する。

- **Test Case 1: 有効なアイテムのカウント**

    - **内容:** コンテナ内に有効なアイテム（リンクと十分なテキストを持つ）と無効なアイテムが混在している場合に、有効なものだけをカウントする。

    - **入力:** `_find_result_container`がコンテナを返し、その中に有効・無効な子要素が含まれる`DOMTreeSt`。

    - **期待値:** 有効なアイテム数（例: 2）が`result_count`に設定され、`result_items`にそのノードが含まれること。

- **Test Case 2: コンテナが見つからない場合**

    - **内容:** `_find_result_container`が`None`を返した場合、結果が0件として処理されること。

    - **入力:** `_find_result_container`が`None`を返すような`DOMTreeSt`。

    - **期待値:** `result_count`が0に設定されること。

- **Test Case 3: 有効なアイテムがない場合**

    - **内容:** コンテナは見つかるが、その中に有効なアイテムが一つもない場合。

    - **入力:** コンテナ内にリンクや十分なテキストを持たない子要素のみが含まれる`DOMTreeSt`。

    - **期待値:** `result_count`が0に設定されること。



---



### 3.6. `core.py` (インテグレーションテスト)



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



**Test Case 2: エラーハンドリングと代替パス (Error Handling and Alternate Paths)**



- **目的:** `extract_main_content`が、処理中のさまざまな失敗シナリオや代替フローを正しく処理できることを確認する。

- **シナリオ 1: robots.txtによるクロール禁止**

    - **内容:** `robots.txt`によって対象URLのスクレイピングが禁止されている場合、関数が早期に`None`を返して処理を終了することを確認する。

    - **入力:** `is_scraping_allowed`が`False`を返すようにモック。

    - **期待値:** `None`が返されること。

- **シナリオ 2: ページ設定の失敗**

    - **内容:** `setup_page`が`None`を返した場合（ページの読み込み失敗など）、関数が`None`を返して処理を終了することを確認する。

    - **入力:** `setup_page`が`None`を返すようにモック。

    - **期待値:** `None`が返されること。

- **シナリオ 3: DOMツリー構築の失敗**

    - **内容:** `make_tree`が`None`を返した場合、関数が`None`を返して処理を終了することを確認する。

    - **入力:** `make_tree`が`None`を返すようにモック。

    - **期待値:** `None`が返されること。

- **シナリオ 4: メインコンテンツ候補なし**

    - **内容:** `MainContentScorer.find_candidates`が空のリストを返した場合、関数が`None`を返して処理を終了することを確認する。

    - **入力:** `find_candidates`が`[]`を返すようにモック。

    - **期待値:** `None`が返されること。

- **シナリオ 5: ページネーションによる再帰呼び出し**

    - **内容:** `WebTypeCHK`が新しい`watch_url`（次のページ）を検知した場合、`extract_main_content`が新しいURLで自身を再帰的に呼び出すことを確認する。

    - **入力:** `WebTypeCHK`のモックが新しいURLを返す。

    - **期待値:** 内部で`setup_page`が2回呼び出され、2回目の呼び出しが新しいURLで行われること。

- **シナリオ 6: 再スコアリングでスコアが改善しない**

    - **内容:** 再評価ループにおいて、子要素のスコアが親要素のスコアを上回らない場合、ループが正しく終了し、親要素が最終コンテンツとして返されることを確認する。

    - **入力:** `rescore_main_content_with_children`が親よりスコアの低い子を返すようにモック。

    - **期待値:** ループが1回で終了し、親ノードが返されること。

- **シナリオ 7: 再スコアリングが最大ループ回数に到達**

    - **内容:** スコアの改善が続き、再評価ループが最大回数（`max_loop_count`）に達した場合に、ループが強制的に終了することを確認する。

    - **入力:** `rescore_main_content_with_children`が常にスコアの高い子を返すようにモック。

    - **期待値:** ループが`max_loop_count`で停止し、その時点での最良のノードが返されること。



- **Test Case 3: CSSセレクタとセレクタリストの生成**

    - **目的:** `extract_main_content`が最終的に選択されたメインコンテンツの`css_selector`および`css_selector_list`を正しく生成し、格納することを確認する。特に、コンテンツが葉ノード（子要素を持たない）である場合の`css_selector_list`の挙動を検証する。

    - **シナリオ:** 絞り込みループを通じて最終的に子要素を持たない葉ノード（例: `<p>`タグ）がメインコンテンツとして選択されるようなモック設定を行う。

    - **入力:**

        - `make_tree`が、複数の階層を持ち、最終的に`<p>`タグが選ばれるようなDOMツリーを返すようにモックする。

        - `rescore_main_content_with_children`は、`extract_main_content_refinement_loop`と同様に、`div.section -> article#main-article -> p.content`と絞り込んでいくようにモックし、`p.content`の子要素は空リストを返すように設定する。

    - **期待値:**

        - 返される`final_content`が`<p>`タグのノードであること。

        - `final_content.css_selector`が`p`タグの正確なCSSセレクタ（例: `'div#main-article > p.content'`）であること。

        - `final_content.css_selector_list`が、`final_content.css_selector`のみを含むリストであること（葉ノードであるため、他の子孫セレクタは生成されない）。

---

### 3.10. `test_integration_extract.py` (実ブラウザ結合テスト)

**目的:** 実ブラウザ（Playwright Chromium）とローカルHTTPサーバー（`ThreadingHTTPServer`）を用いて、固定HTMLページに対する `extract_main_content`（Full スキャン）および `quick_extract_content`（Quick スキャン）を `make_tree` からスコアリングまで通しで検証する。

**前提条件・実行マーカー:**
- ファイル全体に `@pytest.mark.integration` を付与している。
- Chromium が未導入の環境では `pytest.skip` により自動スキップされる（CI では `playwright install --with-deps chromium` で導入）。
- テスト分離のため `content_extractor.core.save_json` をモックし、テスト前後で `playwright_helpers._ROBOTS_CACHE` をクリアする。
- 結合テストのみを実行する場合は `pytest -m integration`、除外する場合は `pytest -m "not integration"` を使用する。

- **Test Case 1: Full スキャンによる本文リンクのみの抽出 (`test_full_scan_extracts_article_links_only`)**
    - **内容:** ナビゲーション・本文（記事8件）・フッターを含む固定HTMLページに対して `extract_main_content` を実行し、本文の記事リンクのみが抽出されることを確認する。
    - **入力:** `/nav/...`, `/article/0.html`〜`7.html`, `/footer/...` を含むHTMLを配信するローカルHTTPサーバーのURLと実ブラウザ。
    - **期待値:** 戻り値が `None` でなく、`links` が空でなくすべて `"/article/"` を含み、`css_selector` が生成されていること。

- **Test Case 2: Full スキャンのセレクタを用いた Quick スキャンの再現 (`test_quick_scan_reuses_selector_from_full_scan`)**
    - **内容:** `extract_main_content` で取得した `css_selector_list` と `web_type` を使って `quick_extract_content` を実行し、同一ページから同じリンクが取得できることを確認する。
    - **入力:** 同一URLと、Full スキャンで得られた `css_selector_list`・`web_type`。
    - **期待値:** `quick_extract_content` の戻り値が `None` でなく、`quick.links == full.links` であること。

- **Test Case 3: 本文リンク更新時の Quick スキャン検知 (`test_quick_scan_detects_changed_links`)**
    - **内容:** Full スキャン後にページ本文のリンクを書き換えた場合、Quick スキャンが変更後のリンクを抽出することを確認する。
    - **入力:** リンクプレフィックスを `"/article/"` から `"/article-v2/"` に変更したHTMLページと、初回 Full スキャンのセレクタ。
    - **期待値:** `quick.links != full.links` であり、抽出されたリンクがすべて `"/article-v2/"` を含むこと。

- **Test Case 4: 重複クラス存在時のプライマリセレクタ一意性 (`test_saved_primary_selector_matches_exactly_one_element`)**
    - **内容:** 同一クラス名（`card`）を持つ兄弟要素が複数存在するページでも、保存される `css_selector` がページ内でちょうど1件にのみヒットすることを確認する。
    - **入力:** `class="card"` を持つ3つの `div` 要素を含むHTMLページ。
    - **期待値:** `page.locator(result.css_selector).count() == 1` であること。

- **Test Case 5: `robots.txt` 禁止パスでの Full / Quick スキャン抑止 (`test_robots_txt_disallow_blocks_full_and_quick_scan`)**
    - **内容:** `robots.txt` で禁止されたパスに対しては、Full スキャン・Quick スキャンともにアクセスを行わず `None` を返すことを確認する。
    - **入力:** `User-agent: *\nDisallow: /private/` を含む `robots.txt` と `/private/index.html` のURL。
    - **期待値:** `extract_main_content` と `quick_extract_content` のいずれも `None` を返すこと。

## 4. 新規テストの追加手順



新しいテストを追加する際は、以下の手順に従います。これにより、設計と実装の同期を保ちます。



1.  **設計書の更新:**

    本ドキュメント（`docs/test/test_design_content_extractor.md`）に、テスト対象の関数と具体的なテストケース（目的、入力、期待値）を追記します。



2.  **テストコードの実装:**

    対応するテストファイル（例: `test/test_scorer.py`）に、設計書に追記したテストケースを実装します。docstringのコメントで、設計書のどのテストケースに対応するかを明記します。



3.  **テストの実行と確認:**

    `pyproject.toml` の `[tool.pytest.ini_options]` で `pythonpath = ["."]` が設定されているため、`PYTHONPATH` の手動設定は不要です。プロジェクトルートで `pytest`（または `uv run --no-sync pytest`）を実行し、追加したテストを含め、すべてのテストが成功することを確認します。



## 5. テストデータと実行



-   **テストデータ:** `DOMTreeSt`と`BoundingBox`を`dataclass`からインポートし、テストケースごとにオブジェクトを生成して利用する。

-   **実行方法:** `pyproject.toml` で `pythonpath = ["."]` が設定されているため、`PYTHONPATH` を指定せずにプロジェクトのルートディレクトリで `pytest`（または `uv run --no-sync pytest`）を実行する。結合テストのみを実行する場合は `pytest -m integration`、除外する場合は `pytest -m "not integration"` を使用する。



## 6. エラー処理とエッジケースの考慮



-   **目的**: 予期せぬ入力やエラー条件に対するシステムの挙動を検証し、堅牢性を高める。また、明示的に文書化されていない追加のエッジケースやシナリオもテストスイートに含まれており、積極的なテストが行われていることを示しています。

-   **検討事項**:

    *   **無効な入力値**: スコアリング関数 (`_calculate_screen_occupancy_multiplier`, `_score_link_length`, `_score_text_length`) における数値の範囲外 (`occupancy_rate`が負の値や1.0超)、`None`値、不正な型 (`DOMTreeSt`以外) の入力に対するテスト。

    *   **空のデータ**: `make_tree`が空のDOMツリーや`None`を返した場合、`MainContentScorer`が候補を全く見つけられなかった場合の`extract_main_content`の挙動。

    *   **例外処理**: 特定の操作で例外が発生した場合のハンドリング（例: 外部リソースへのアクセス失敗）。

## 7. パフォーマンス要件とテストの検討

-   **目的**: 大規模なDOMツリーや複雑なWebページからのコンテンツ抽出におけるパフォーマンス特性を理解し、最適化の指針を得る。
-   **検討事項**:
    *   **測定**: 処理時間、メモリ使用量などの主要なパフォーマンスメトリクスの特定と測定方法。
    *   **シナリオ**: 非常に長いHTMLドキュメント、多数のノードを持つDOMツリー、深すぎるDOM階層など、パフォーマンスに影響を与える可能性のあるシナリオの定義。
    *   **ツール**: `pytest-benchmark`などのパフォーマンス測定ツールの導入検討。
    *   **CI/CDとの連携**: パフォーマンス回帰を早期に検出するためのCI/CDパイプラインへの統合。

## 8. 設定/定数のテスト

-   **目的**: モジュールの挙動を制御する主要な設定値や定数（例: `_score_link_length`の`MEAN`値、`calculate_depth_weight`の`max_depth`や`weight_factor`など）がシステム全体に与える影響を理解する。
-   **検討事項**:
    *   **感度分析**: 各定数を変更した場合にスコアリング結果や抽出されるコンテンツがどのように変化するかを評価するテスト。
    *   **境界値テスト**: 定数の極端な値（最大/最小）がシステムに与える影響の検証。
    *   **ドキュメント化**: これらの定数の選択理由、影響範囲、推奨値の範囲を明確にドキュメント化する。

## 9. 依存関係の明確化

-   **目的**: `content_extractor`モジュール内の各コンポーネントおよび外部ライブラリへの依存関係を明確にし、テスト戦略におけるモックの必要性を特定する。
-   **検討事項**:
    *   **内部依存**: `core.py`が`make_tree`や`MainContentScorer`に依存するように、モジュール内の関数やクラス間の依存関係の図示または記述。
    *   **外部依存**: Playwright、`dataclasses`、`math`などの外部ライブラリへの依存。PlaywrightのようなI/Oが絡む依存は`unittest.mock`で置き換える方針を再確認。
    *   **モック戦略**: どの依存をモックし、どの依存を実体としてテストするかに関する具体的なガイドライン。

## 10. テストデータの管理戦略

-   **目的**: 複雑なテストケース（特に結合テスト）に必要なテストデータを効率的に作成、管理、再利用するための方法論を確立する。
-   **検討事項**:
    *   **データ構造**: `DOMTreeSt`や`BoundingBox`オブジェクトを生成するための構造化されたアプローチ（例: ファクトリ関数、`pytest`フィクスチャ）。
    *   **外部データファイル**: 大規模なDOMツリー構造を表現するために、JSONやHTMLファイルとしてテストデータを外部化する検討。
    *   **データの匿名化**: 実際のWebサイトから取得したデータを使用する場合の個人情報保護や機密情報保護に関する配慮。
    *   **テストデータセットのバージョン管理**: テストデータがコードの変更と同期していることを保証する方法。

## 11. テストカバレッジの目標

-   **目的**: テストスイートの網羅性を評価し、主要なコードパスが適切にテストされていることを確認する。
-   **検討事項**:
    *   **目標値の設定**: 目標とするカバレッジ率（例: ステートメント、ブランチ、関数カバレッジ）。
    *   **ツール**: `coverage.py`や`pytest-cov`の導入と活用。
    *   **CI/CDへの統合**: カバレッジレポートの生成と閾値チェックをCI/CDパイプラインに組み込む。

## 12. 「メインコンテンツ」の定義

-   **目的**: `content_extractor`が特定しようとする「メインコンテンツ」の概念を明確化し、テストケースの設計および結果の評価基準を確立する。
-   **検討事項**:
    *   **基準**: メインコンテンツを構成する一般的な特性（例: 主要なテキストブロック、画像、動画、特定のHTML要素構造、画面占有率の高さ）の定義。
    *   **除外対象**: メインコンテンツではないと見なされる要素（例: ナビゲーション、広告、フッター、サイドバー）の定義。
    *   **ユースケース**: 異なるタイプのWebページ（ブログ記事、ニュースサイト、商品ページなど）におけるメインコンテンツの具体的な例。
