"""検索結果ページの品質評価（SQS）。監視本流から分離した任意機能。"""

from .evaluate import evaluate_search_quality, run_search_quality_evaluation_standalone

__all__ = [
    "evaluate_search_quality",
    "run_search_quality_evaluation_standalone",
]
