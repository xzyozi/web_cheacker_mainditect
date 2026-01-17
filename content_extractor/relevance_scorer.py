import math
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim
from typing import List

from .dom_treeSt import DOMTreeSt
from .config import QUALITY_SCORING_CONFIG
from setup_logger import setup_logger

logger = setup_logger("relevance_scorer")

class RelevanceScorer:
    """
    検索クエリと結果アイテムリストの関連性をスコアリングするクラス。
    """
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        """
        Args:
            model_name (str): sentence-transformersで使用する事前学習済みモデル名。
        """
        try:
            # モデルは比較的高価な処理なので、インスタンス生成時に一度だけロードする
            self.semantic_model = SentenceTransformer(model_name)
        except Exception as e:
            logger.error(f"SentenceTransformerモデルの読み込みに失敗しました: {e}")
            # アプリケーションを停止させるか、明確なエラーを投げる
            raise ImportError("SentenceTransformerの初期化に失敗しました。`pip install sentence-transformers` を確認してください。") from e
        self.tfidf_vectorizer = TfidfVectorizer()

    def _calculate_jaccard(self, text1: str, text2: str) -> float:
        """2つのテキスト間のジャカード類似度を計算します。"""
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union != 0 else 0.0

    def score_relevance(self, query: str, items: List[DOMTreeSt]) -> List[DOMTreeSt]:
        """各アイテムの関連性スコアを計算し、DOMTreeStオブジェクトを更新します。"""
        if not items or not self.semantic_model:
            return items

        # 各アイテムからテキストを抽出 (タイトルやスニペットを想定)
        item_texts = [item.text for item in items]

        # 1. TF-IDF + Cosine Similarity
        tfidf_matrix = self.tfidf_vectorizer.fit_transform(item_texts + [query])
        tfidf_scores = cosine_similarity(tfidf_matrix[:-1], tfidf_matrix[-1]).flatten()

        # 2. Semantic Similarity (Sentence Transformers)
        query_embedding = self.semantic_model.encode(query)
        item_embeddings = self.semantic_model.encode(item_texts)
        # sentence_transformers.util.cos_sim を使用して、より効率的に計算
        semantic_scores = cos_sim(query_embedding, item_embeddings)[0].tolist()

        for i, item in enumerate(items):
            # 3. Jaccard Similarity
            jaccard_score = self._calculate_jaccard(query, item.text)
            
            # 4. ハイブリッドスコアの計算 (重みは設定ファイルで管理することを推奨)
            relevance_score = (
                (0.2 * jaccard_score) +
                (0.3 * tfidf_scores[i]) +
                (0.5 * float(semantic_scores[i]))  # numpy.float32をfloatにキャスト
            )
            item.relevance_score = relevance_score
        
        return items

    def calculate_sqs(self,
                      result_count: int,
                      avg_relevance: float,
                      relevance_variance: float,
                      max_relevance: float) -> tuple[float, str]:
        """SQSスコアと品質カテゴリを計算して返す。"""
        if result_count == 0:
            return 0, "Invalid/Empty"

        weights = QUALITY_SCORING_CONFIG['sqs_weights']
        thresholds = QUALITY_SCORING_CONFIG['sqs_thresholds']

        # SQS計算式の各項を計算
        count_score = math.log(result_count + 1) * weights['result_count']
        avg_rel_score = avg_relevance * weights['avg_relevance']
        variance_penalty = relevance_variance * weights['relevance_variance']
        max_rel_score = max_relevance * weights['max_relevance']

        # SQSを計算 (スケールを100点満点に調整)
        sqs = (count_score + avg_rel_score - variance_penalty + max_rel_score) * 100
        sqs_score = max(0, sqs)  # 負の値にならないようにする

        # 最終分類
        if sqs_score >= thresholds['valid']:
            quality_category = "Valid"
        elif sqs_score >= thresholds['low_quality']:
            quality_category = "Low Quality"
        else:
            quality_category = "Invalid/Empty"
        
        logger.info(f"SQS: {sqs_score:.2f}, Category: {quality_category}")
        
        return sqs_score, quality_category