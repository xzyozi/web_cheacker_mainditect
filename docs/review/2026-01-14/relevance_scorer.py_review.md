# `relevance_scorer.py` Review

This module represents the most technically advanced and sophisticated part of the scraping system. It aims to score the relevance of extracted content against a search query using a hybrid of classic and modern NLP techniques. The implementation of a "Search Quality Score" (SQS) is a powerful concept for automatically assessing the utility of a search result page.

### 良い点 (Good Practices)

1.  **ハイブリッドな関連性スコアリング**: `score_relevance` 関数は、3つの異なるアプローチを組み合わせて関連性を評価しています。
    *   **Jaccard Similarity**: 古典的だが高速で、単語の完全一致を評価するのに有効。
    *   **TF-IDF + Cosine Similarity**: 単語の頻度と逆文書頻度を考慮し、キーワードの重要性を評価する、堅牢な統計的手法。
    *   **Semantic Similarity (Sentence Transformers)**: `all-MiniLM-L6-v2`のような強力な事前学習済みモデルを使い、単語の表面的な一致だけでなく、文全体の意味的な類似性を捉えることができる最先端のアプローチ。
    この3つを組み合わせることで、各手法の長所を活かし、短所を補い合う、非常に強力な関連性評価が可能です。
2.  **高価なモデルの効率的なロード**: `SentenceTransformer` モデルのロードは時間がかかる処理ですが、`RelevanceScorer` クラスのコンストラクタ (`__init__`) で一度だけロードするように設計されています。これにより、インスタンスが再利用される限り、スコアリングのたびにモデルをロードし直すという非効率な処理を回避できます。
3.  **SQS (Search Quality Score) の概念**: `calculate_sqs` 関数は、単に個々のアイテムの関連性だけでなく、「結果の数」「平均関連性」「関連性のばらつき」「最大関連性」といった複数の指標を組み合わせて、検索結果ページ全体の品質を একটি（ひとつの）数値で評価しようとしています。これは非常に高度で価値のある試みです。
4.  **設定の外部化**: SQSの計算に使う重み (`weights`) や閾値 (`thresholds`) を `config.py` から取得しており、コードを変更することなくスコアリングのロジックを微調整できる、優れた設計です。

---

### 改善・修正提案 (Code Review)

#### 1. SentenceTransformer のエラー処理と依存関係

`__init__` 内でモデルのロードに失敗した場合、`self.semantic_model = None` としていますが、その後の `score_relevance` では `if not self.semantic_model:` というチェックがあるだけで、すぐに処理を終了してしまいます。これでは、モデルのロード失敗が単に「スコアリングが行われない」という結果になるだけで、なぜ失敗したのかが呼び出し元に伝わりません。

また、`sentence-transformers` は重量級のライブラリであり、このプロジェクトの必須の依存関係とすべきか、それともオプションの依存関係とすべきかを明確にする必要があります。

**修正案:**

*   **案A (必須依存とする場合):** `__init__` でモデルのロードに失敗した場合は、例外を発生させてプログラムを停止させるべきです。これにより、環境設定の不備（ライブラリがインストールされていない、モデルがダウンロードできないなど）を早期に検知できます。

    ```python
    # in __init__
    try:
        self.semantic_model = SentenceTransformer(model_name)
    except Exception as e:
        logger.error(f"SentenceTransformerモデルの読み込みに失敗しました: {e}")
        # アプリケーションを停止させるか、明確なエラーを投げる
        raise ImportError("SentenceTransformerの初期化に失敗しました。`pip install sentence-transformers` を確認してください。") from e
    ```

*   **案B (オプション依存とする場合):** `score_relevance` の中で `self.semantic_model` が `None` の場合、意味的類似性スコアの計算をスキップし、TF-IDFとJaccardだけでスコアを計算するフォールバックロジックを実装します。重みもそれに応じて調整する必要があります。

#### 2. `score_relevance` 内のバッチ処理

`SentenceTransformer` の `encode` メソッドは、テキストのリストを一度に処理する（バッチ処理）ことで、GPUを効率的に利用し、パフォーマンスを大幅に向上させます。現在のコードはすでにリスト (`item_texts`) を渡しており、この点は正しく実装されています。

ただし、`cosine_similarity` の計算で `cpu()` を呼び出していますが、`encode` の `convert_to_tensor=True` はPyTorchのテンソルを返します。もしGPUが利用可能な環境で実行する場合、`cpu()` を呼び出すとGPUからCPUへのデータ転送が発生し、ボトルネックになる可能性があります。

**修正案:**

`SentenceTransformer` はデバイスの自動検出を行うため、`cpu()` を明示的に呼び出す必要はありません。PyTorchのテンソルをそのまま `cosine_similarity` に渡すか、あるいは `sentence_transformers.util.cos_sim` を使うとよりシンプルに書けます。

```python
# Before
# query_embedding = self.semantic_model.encode(query, convert_to_tensor=True)
# item_embeddings = self.semantic_model.encode(item_texts, convert_to_tensor=True)
# semantic_scores = cosine_similarity(item_embeddings.cpu(), query_embedding.cpu().reshape(1, -1)).flatten()

# After (using sentence_transformers.util)
from sentence_transformers.util import cos_sim

query_embedding = self.semantic_model.encode(query)
item_embeddings = self.semantic_model.encode(item_texts)
semantic_scores = cos_sim(query_embedding, item_embeddings)[0].numpy() # or .tolist()
```

#### 3. `calculate_sqs` の入力

この関数は `DOMTreeSt` ノードを受け取りますが、実際に使用しているのは `result_count`, `avg_relevance`, `relevance_variance`, `max_relevance` といった、すでに関連性スコアリングが完了していることを前提としたフィールドです。

これは少し密結合であり、`calculate_sqs` を単体でテストするのが難しくなります。

**修正案（よりクリーンな設計へ）:**

`calculate_sqs` が必要とする値を直接引数として受け取るようにシグネチャを変更することを検討します。

```python
# Before
def calculate_sqs(self, node: DOMTreeSt) -> DOMTreeSt:
    # ... uses node.result_count, node.avg_relevance, etc.

# After (推奨)
def calculate_sqs(self,
                  result_count: int,
                  avg_relevance: float,
                  relevance_variance: float,
                  max_relevance: float) -> tuple[float, str]:
    """SQSスコアと品質カテゴリを計算して返す。"""
    if result_count == 0:
        return 0, "Invalid/Empty"

    # ... SQS calculation logic ...
    
    sqs = ...
    category = ...
    return sqs, category

# 呼び出し側でDOMTreeStノードを更新する
# sqs, category = scorer.calculate_sqs(...)
# node.sqs_score = sqs
# node.quality_category = category
```

これにより、`calculate_sqs` は `DOMTreeSt` という複雑なオブジェクトに依存しない純粋な計算関数となり、テストが容易になります。
