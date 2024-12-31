# +----------------------------------------------------------------
# + get domain name
# +----------------------------------------------------------------
from urllib.parse import urlparse

def get_domain(url):
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    return domain

# +----------------------------------------------------------------
# file edit faction
# +----------------------------------------------------------------
import os
def util_handle_path(path, custom_filename=None):
    """
    指定されたパスに基づいて以下の操作を行います:
    - パスに拡張子が含まれる場合: ファイルを作成または取得します。
    - パスに拡張子が含まれず、カスタムファイル名が指定されている場合: カスタム名のファイルを作成します。
    - パスに拡張子が含まれず、カスタムファイル名が指定されていない場合: ディレクトリを作成します。

    Args:
        path (str): ファイルまたはディレクトリのパス。
        custom_filename (str, optional): ファイル作成時のカスタム名。

    Returns:
        str: 作成または取得したファイル/ディレクトリのパス。エラーが発生した場合は None を返します。
    """
    directory, filename = os.path.split(path)
    extension = os.path.splitext(filename)[-1]

    if extension:  # パスに拡張子が含まれる場合 -> ファイルの処理
        return _create_file(path)

    if custom_filename:  # パスに拡張子がなくカスタムファイル名が指定されている場合
        return _create_file(os.path.join(directory, custom_filename))

    # パスに拡張子がなくカスタムファイル名も指定されていない場合 -> ディレクトリの処理
    return _create_directory(path)

def _create_file(file_path):
    """指定されたパスにファイルを作成します (存在しない場合)。"""
    if os.path.isfile(file_path):
        return file_path

    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as file:
            file.write('')
        os.chmod(file_path, 0o755)
        print(f"ファイル '{file_path}' を作成しました。")
        return file_path
    except IOError as e:
        print(f"ファイル '{file_path}' を作成できませんでした: {e.strerror}")
        return None

def _create_directory(dir_path):
    """指定されたパスにディレクトリを作成します (存在しない場合)。"""
    if os.path.isdir(dir_path):
        print(f"ディレクトリ '{dir_path}' はすでに存在します。")
        return dir_path

    try:
        os.makedirs(dir_path)
        os.chmod(dir_path, 0o755)
        print(f"ディレクトリ '{dir_path}' を作成しました。")
        return dir_path
    except OSError as e:
        print(f"ディレクトリ '{dir_path}' を作成できませんでした: {e.strerror}")
        return None
