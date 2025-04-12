import logging
import copy
import sys
import os
from logging.handlers import RotatingFileHandler

# カスタムログレベルを追加
NOTICE_LEVEL = logging.INFO + 2
ALERT_LEVEL = logging.INFO + 4

logging.addLevelName(NOTICE_LEVEL, "NOTICE")
logging.addLevelName(ALERT_LEVEL, "ALERT")

# ログレベルのカスタムメソッド追加
def notice(self, message, *args, **kwargs):
    if self.isEnabledFor(NOTICE_LEVEL):
        self._log(NOTICE_LEVEL, message, args, **kwargs)

def alert(self, message, *args, **kwargs):
    if self.isEnabledFor(ALERT_LEVEL):
        self._log(ALERT_LEVEL, message, args, **kwargs)

logging.Logger.notice = notice
logging.Logger.alert = alert

# # カスタムログレベルを追加
# NOTICE_LEVEL = logging.INFO + 2
# ALERT_LEVEL = logging.INFO + 4

# logging.addLevelName(NOTICE_LEVEL, "NOTICE")
# logging.addLevelName(ALERT_LEVEL, "ALERT")

# # ログレベルのカスタムメソッド追加
# def notice(self, message, *args, **kwargs):
#     if self.isEnabledFor(NOTICE_LEVEL):
#         self._log(NOTICE_LEVEL, message, args, **kwargs)

# def alert(self, message, *args, **kwargs):
#     if self.isEnabledFor(ALERT_LEVEL):
#         self._log(ALERT_LEVEL, message, args, **kwargs)

# logging.Logger.notice = notice
# logging.Logger.alert = alert

class ColoredFormatter(logging.Formatter):
    """ANSIカラー対応のフォーマッター"""
    COLORS = {
        "DEBUG": "\033[0;36m",  # CYAN
        "NOTICE": "\033[1;34m",  # LIGHT BLUE
        "INFO": "\033[0;32m",  # GREEN
        "ALERT": "\033[0;35m",  # PURPLE
        # "ALERT": "\033[0;35m",  # PURPLE
        "WARNING": "\033[0;33m",  # YELLOW
        "ERROR": "\033[0;31m",  # RED
        "CRITICAL": "\033[0;37;41m",  # WHITE ON RED
        "RESET": "\033[0m",  # RESET COLOR
    }

    def format(self, record):
        colored_record = copy.copy(record)
        levelname = colored_record.levelname
        seq = self.COLORS.get(levelname, self.COLORS["RESET"])
        colored_record.levelname = f"{seq}{levelname}{self.COLORS['RESET']}"
        return super().format(colored_record)

def setup_logger(
    name: str ,
    level: str = "INFO",
    use_colors: bool = True,
    log_file: str = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    custom_levels: dict = None,
) -> logging.Logger:
    """
    汎用的なロガー設定関数

    Args:
        name (str): ロガー名 (デフォルト: "DefaultLogger")
        level (str): ログレベル (デフォルト: "INFO")
        use_colors (bool): ANSIカラーを有効化するか (デフォルト: True)
        log_file (str, optional): ファイル出力のパス (デフォルト: None)
        max_bytes (int, optional): 1ファイルの最大サイズ (デフォルト: 10MB)
        backup_count (int, optional): ログの世代数 (デフォルト: 5)
        custom_levels (dict, optional): カスタムログレベルの追加 (例: {"STATUS": logging.INFO + 5})

    Returns:
        logging.Logger: 設定済みのロガー
    """
    logger = logging.getLogger(name)
    logger.propagate = False

    # カスタムログレベルを追加
    if custom_levels:
        for level_name, level_value in custom_levels.items():
            logging.addLevelName(level_value, level_name)

    # 文字列のログレベルを数値に変換
    level = getattr(logging, level.upper(), logging.DEBUG)
    logger.setLevel(logging.DEBUG)

    # すでにハンドラーがある場合は再設定しない
    if logger.handlers:
        return logger

    # フォーマット設定
    log_format = "[%(filename)s:%(lineno)d %(funcName)s]%(asctime)s[%(levelname)s] - %(message)s"
    date_format = "%H:%M:%S"

    # 標準出力のハンドラー
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = ColoredFormatter(log_format, datefmt=date_format) if use_colors else logging.Formatter(log_format, datefmt=date_format)
    stream_handler.setFormatter(formatter)

    stream_handler.setLevel(logging.INFO)

    logger.addHandler(stream_handler)

    # ファイル出力を追加（必要な場合）
    if log_file:
        log_file = os.path.abspath(log_file)
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)  # ディレクトリ作成
        file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

        file_handler.setLevel(logging.DEBUG)

        logger.addHandler(file_handler)

    return logger
