import json
import os

from . import util_str


def save_json(data: dict, url: str, directory: str = "data") -> None:
    """辞書型のデータを JSON ファイルとして保存する。

    Args:
        data (dict): 保存するデータ
        url (str): データに対応するURL
        directory (str): JSONファイルを保存するディレクトリのパス
    """
    domain = util_str.get_domain(url)
    safe_domain = util_str.sanitize_filename_part(domain) or "unknown"
    file_path = os.path.join(directory, f"{safe_domain}.json")
    util_str.util_handle_path(file_path)  # ファイルを作成または取得する

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
