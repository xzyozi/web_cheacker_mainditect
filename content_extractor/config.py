import os
import json
from setup_logger import setup_logger

logger = setup_logger("content_extractor_config")

def _load_json_config(filename: str, default_config: dict) -> dict:
    """
    指定されたJSON設定ファイルを読み込みます。
    失敗した場合はハードコードされたデフォルト値を返します。
    """
    # このファイルの場所から2つ上のディレクトリ（main）に移動し、そこからの相対パスでconfigを指定
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, 'config', filename)
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"設定を '{CONFIG_FILE_PATH}' から読み込みました。")
        return config
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"設定ファイル '{CONFIG_FILE_PATH}' の読み込みに失敗しました ({e})。デフォルト値を使用します。")
        return default_config

# 「結果なし」判定用の設定
NO_RESULTS_DEFAULT = {
    "keywords": [
        "検索結果がありません", "該当する情報は見つかりませんでした", "no results found",
        "nothing found", "we couldn't find anything", "お探しのページは見つかりませんでした",
        "ページが見つかりません", "404 not found"
    ],
    "no_results_selectors": [ ".no-results", "#no-results-message", "[data-qa='no-results-found']", ".empty-state" ],
    "expected_results_selectors": [ ".search-results", ".results-list", "#search-results-container" ]
}
NO_RESULTS_CONFIG = _load_json_config('no_results_config.json', NO_RESULTS_DEFAULT)

# 品質スコアリング用の設定
QUALITY_SCORING_DEFAULT = {
    "sqs_weights": {
        "result_count": 0.2,
        "avg_relevance": 0.4,
        "relevance_variance": 0.2,
        "max_relevance": 0.2
    },
    "sqs_thresholds": {
        "valid": 60,
        "low_quality": 20
    }
}
QUALITY_SCORING_CONFIG = _load_json_config('quality_config.json', QUALITY_SCORING_DEFAULT)