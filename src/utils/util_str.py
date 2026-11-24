import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def get_domain(url: str) -> str:
    """URL からホスト部（netloc）を返す。"""
    parsed_url = urlparse(url)
    return parsed_url.netloc


def sanitize_filename_part(value: str) -> str:
    """ファイル名に使用できない文字（ポート番号の `:` 等）を `_` に置換する。"""
    return _INVALID_FILENAME_CHARS_RE.sub("_", value)


def ensure_file(file_path: str) -> Optional[str]:
    """指定されたパスに空ファイルを作成する（未存在時のみ）。失敗時は None を返す。"""
    if os.path.isfile(file_path):
        return file_path

    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as file:
            file.write("")
        logger.info(f"ファイル '{file_path}' を作成しました。")
        return file_path
    except OSError as e:
        logger.error(f"ファイル '{file_path}' を作成できませんでした: {e}")
        return None


def ensure_dir(dir_path: str) -> Optional[str]:
    """指定されたパスにディレクトリを作成する（未存在時のみ）。失敗時は None を返す。"""
    if os.path.isdir(dir_path):
        logger.debug(f"ディレクトリ '{dir_path}' はすでに存在します。")
        return dir_path

    try:
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"ディレクトリ '{dir_path}' を作成しました。")
        return dir_path
    except OSError as e:
        logger.error(f"ディレクトリ '{dir_path}' を作成できませんでした: {e}")
        return None


def util_handle_path(path: str, custom_filename: Optional[str] = None) -> Optional[str]:
    """指定されたパスに基づいてファイルまたはディレクトリを作成・取得する。

    - 末尾がパス区切り文字（`/` または `\\`）の場合:
      ディレクトリとして扱う（`custom_filename` 指定時はその配下のファイル）。
    - パスに拡張子が含まれる場合: ファイルを作成または取得します。
    - パスに拡張子が含まれず、カスタムファイル名が指定されている場合: カスタム名のファイルを作成します。
    - パスに拡張子が含まれず、カスタムファイル名が指定されていない場合: ディレクトリを作成します。
    """
    if path.endswith(("/", "\\")):
        if custom_filename:
            return _create_file(os.path.join(path, custom_filename))
        return _create_directory(path)

    directory, filename = os.path.split(path)
    extension = os.path.splitext(filename)[-1]

    if extension:  # パスに拡張子が含まれる場合 -> ファイルの処理
        return _create_file(path)

    if custom_filename:  # パスに拡張子がなくカスタムファイル名が指定されている場合
        return _create_file(os.path.join(directory, custom_filename))

    # パスに拡張子がなくカスタムファイル名も指定されていない場合 -> ディレクトリの処理
    return _create_directory(path)


def _create_file(file_path: str) -> Optional[str]:
    """指定されたパスにファイルを作成します (存在しない場合)。"""
    return ensure_file(file_path)


def _create_directory(dir_path: str) -> Optional[str]:
    """指定されたパスにディレクトリを作成します (存在しない場合)。"""
    return ensure_dir(dir_path)
