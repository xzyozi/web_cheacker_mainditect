# `scorer.py` Review

This module implements the core logic for identifying the main content of a webpage by assigning a heuristic-based score to each DOM node. The `MainContentScorer` class uses a sophisticated combination of factors, including element size, position, depth, text length, and link count. The use of statistical distributions (`scipy.stats`) and Gaussian functions to model ideal properties is a very advanced and impressive technique.

### 良い点 (Good Practices)

1.  **高度なヒューリスティックスコアリング**: このモジュールは、単純なルールベースのシステムを遥かに超えています。
    *   **画面占有率の評価 (`_calculate_screen_occupancy_multiplier`)**: ガウス関数を使って「理想的な画面占有率」を定義し、そこから外れる要素のスコアを減衰させるというアプローチは非常にスマートです。これにより、大きすぎる（ヘッダーやフッターなど）または小さすぎる（アイコンなど）要素のスコアを効果的に下げることができます。
    *   **位置とサイズの確率分布**: `scipy.stats` を使って、要素のX/Y座標や幅/高さの「理想的な分布」を定義し、それにどの程度一致するかでスコアを付けているのは、非常に独創的で強力な方法です。これにより、「ページの真ん中あたりにある、横幅が広い要素」が高く評価されるようになります。
    *   **非線形な重み付け**: `score_text_length` や `calculate_depth_weight` などで、`math.exp` やべき乗 (`**`) を使ってスコアを非線形に変化させています。これにより、特定の特徴がスコアに与える影響を細かく調整できます。
2.  **クラスベースの設計**: スコアリングロジックが `MainContentScorer` というクラスにカプセル化されており、状態（`tree`, `width`, `height`）をインスタンス変数として保持しています。これにより、スコアリングのプロセスが整理され、再利用しやすくなっています。
3.  **関数の分離**: テキスト長、リンク数、深さのスコアを計算するロジックが、それぞれ独立した小さな関数 (`score_text_length`, `score_link_length`, `calculate_depth_weight`) に分割されています。これにより、各スコアリング要素が何をしているのかが分かりやすくなっています。

---

### 改善・修正提案 (Code Review)

#### 1. グローバル定数とマジックナンバー (重要)

モジュールの下部に、多数のグローバル定数 (`X_DIST`, `WEIGHTS`, `WeightBox`, `TEXT_LENGTH_MEAN`など) が定義されています。これらはスコアリングアルゴリズムの心臓部ですが、グローバルスコープに散在しているため、管理が難しくなっています。

-   `WeightBox` クラスは `BoundingBox` を継承していますが、インスタンス化されず、単にクラス変数（静的プロパティ）のコンテナとして使われています。これは少し紛らわしい使い方です。
-   `X_DIST`, `Y_DIST`, `WIDTH_DIST` といった分布オブジェクトがグローバルに作成されています。
-   `_score_node` 内で、`min(h, 0.9)` や `node.score += 0.5` のような「マジックナンバー」がハードコードされており、これが何を表すのかが直感的に分かりにくいです。

**修正案:**

これらの定数をすべて `MainContentScorer` クラスのクラス変数またはインスタンス変数としてまとめるか、専用の`ScoringConfig`のようなデータクラスに集約することを強く推奨します。

```python
# After (推奨案)
class MainContentScorer:
    # --- Scoring Parameters ---
    X_DIST = stats.norm(0.5, 0.35)
    Y_DIST = stats.norm(0.5, 0.35)
    WIDTH_DIST = stats.gamma(6.7, scale=0.11)
    
    class Weights:
        X = 1
        Y = 1
        WIDTH = 1
        HEIGHT = 1.5
        MAIN_TAG_BONUS = 0.5
        MAX_NORMALIZED_HEIGHT = 0.9

    def __init__(self, ...):
        # ...

    def _score_node(self, node: DOMTreeSt, ...):
        # ...
        # w_score = self.WIDTH_DIST.pdf(w) ** self.Weights.WIDTH
        # h_score = min(h, self.Weights.MAX_NORMALIZED_HEIGHT) ** self.Weights.HEIGHT
        # ...
        # if is_main_element(node):
        #     node.score += self.Weights.MAIN_TAG_BONUS
```

これにより、スコアリングのパラメータが一箇所にまとまり、見通しが良くなり、調整も容易になります。

#### 2. `_score_node` 関数の責務過多と複雑さ

`_score_node` は非常に多くのことを行っています。深さの初期化、リンクスコアの計算、画面占有率の計算、位置・サイズのスコアリング、深さのスコアリング、最終スコアの計算など、多数のロジックが1つの関数に詰め込まれています。また、`pre_mode`, `depth_flag`, `maintag_addscore` といったブール型のフラグ引数があり、関数の呼び出し方によって振る舞いが大きく変わるため、非常に複雑で理解しにくいです。

**修正案:**

-   **フラグ引数の排除**: フラグで振る舞いを変えるのではなく、異なる目的のために別々のメソッドを作成します。例えば、`_score_for_candidacy` と `_score_for_refinement` のように。
-   **ロジックの分割**: スコアの各要素（位置スコア、サイズスコア、テキストスコアなど）を計算する部分を、それぞれ別のプライベートメソッドに切り出します。

```python
# After (ロジック分割の例)
class MainContentScorer:
    # ...
    def _calculate_position_score(self, node: DOMTreeSt) -> float:
        # ...
    
    def _calculate_size_score(self, node: DOMTreeSt) -> float:
        # ...
    
    def _score_node(self, ...):
        # pos_score = self._calculate_position_score(node)
        # size_score = self._calculate_size_score(node)
        # ...
        # node.score = pos_score * size_score * ...
```

#### 3. `__init__` の初期化ロジック

コンストラクタで `self.init_depth_flag = True` を設定し、`_score_node` の初回呼び出し時に `self.parent_depth_diff` を設定するというロジックは、暗黙的な状態変化に依存しており、非常にトリッキーでバグの温床です。もし `_score_node` が意図しない順番で呼ばれた場合、`parent_depth_diff` が予期せぬ値に設定される可能性があります。

**修正案:**

親の深さの差分は、スコアリングを開始するメソッド（例: `score_parent_and_children`）の最初で一度だけ計算し、`_score_node` には引数として渡すようにします。

```python
# After (推奨)
class MainContentScorer:
    # ...
    def _score_node(self, node: DOMTreeSt, depth_diff: int, ...):
        # ...
        depth_weight = calculate_depth_weight(node.depth - depth_diff)
        # ...

    def score_parent_and_children(self) -> list[DOMTreeSt]:
        if not self.tree:
            return []
        
        # ここで深さの基準を計算
        parent_depth_diff = self.tree[0].depth 
        
        scored_nodes: List[DOMTreeSt] = []
        for node in self.tree:
            # 引数として渡す
            self._score_node(node, depth_diff=parent_depth_diff) 
            scored_nodes.append(node)
        
        # ...
```

#### 4. `is_valid_element` のロジック

この関数は、メインコンテンツ候補から除外するタグのリストを持っています。これは一般的なアプローチですが、`"P"` (段落) や `"BLOCKQUOTE"` (引用) といった、明らかに本文コンテンツの一部となりうるタグまで除外してしまっています。これは意図したものでしょうか？ もしこれらのタグを含む要素が候補から外されてしまうと、重要なコンテンツを見逃す可能性があります。

**修正案:**

`invalid_tags` のリストを見直し、本当に本文コンテンツになり得ないタグ（`NAV`, `HEADER`, `FOOTER`, `ASIDE`など）に限定することを検討してください。
