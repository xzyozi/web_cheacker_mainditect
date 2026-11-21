# 🕵️ Web更新チェッカー (Quick/Fullスキャン対応)

## 📌 概要

このツールは、Webページの更新を定期的にチェックするためのPythonスクリプトです。Playwrightを使用してDOM構造を取得し、主要なコンテンツの差分を比較して、変更が検出された場合に通知や記録を行います。

## ✨ 主な機能

- **デュアルスキャンモード:**
    - **Fullスキャン:** DOM構造全体を解析し、主要なコンテンツのセレクタを特定・抽出します。初回スキャンやQuickスキャンが失敗した際に使用されます。
    - **Quickスキャン:** 前回特定されたCSSセレクタを使用して、コンテンツの変更を迅速に確認します。非常に高速ですが、DOM構造の変更に影響を受けやすいです。
- **メール通知:** ページの更新が検出されると、スクリーンショット付きの通知メールを送信します。
- **ユーザーごとの設定:** 複数のユーザープロファイルをサポートしており、それぞれが独自のURLリストと設定を持つことができます。
- **堅牢なエラーハンドリング:** スクリーンショットやネットワークの失敗に対して堅牢に設計されており、アプリケーションの継続的な実行を保証します。
- **詳細なロギング:** すべての操作、エラー、スキャン結果の詳細なログを記録します。

## 📁 ディレクトリ構成

```
main/
│
├─ users/                  # ユーザーごとの設定とデータ
│   ├─ config.yaml         # 共通のメインアプリケーション設定 (ユーザー専用が無い場合に使用)
│   ├─ sample/             # 新規プロファイル作成用のサンプルテンプレート
│   │   ├─ cheacker_url.json.sample
│   │   └─ mail.yaml.sample
│   └─ {ユーザー名}/        # ユーザーディレクトリ (Git管理対象外、例: 'jav')
│       ├─ cheacker_url.json  # 監視対象URLとその状態のリスト (JSON配列)
│       ├─ config.yaml        # このユーザー用のメインアプリケーション設定 (任意・共通設定より優先)
│       └─ mail.yaml          # メール通知設定
│
├─ content_extractor/      # コンテンツ抽出とスキャンのためのコアロジック
├─ data/                   # スクリーンショットなどの永続的なデータを保存するディレクトリ
│   └─ view/               # スクリーンショットの永続的な保存場所
│
├─ log/                    # 実行ログ
│   └─ web-chk_YYYYMMDD_HHMMSS.log
│
├─ mail/                   # メール送信モジュール
├─ text_struct/            # メール用のHTML生成ロジック
│
├─ web-cheackerV3.py       # アプリケーションを実行するためのメインスクリプト
├─ pyproject.toml          # プロジェクト設定および依存関係の定義
├─ uv.lock                 # uv による依存関係ロックファイル
└─ README.md               # このファイル
```

## ⚙️ 要件

このプロジェクトには Python 3.10 以上が必要です。依存関係は `pyproject.toml` と `uv.lock` で管理されており、[`uv`](https://docs.astral.sh/uv/) によるインストールを推奨しています（詳細手順は [docs/setup/python_setup.md](./docs/setup/python_setup.md) を参照）。

**主な依存関係:**
- `pandas`
- `PyYAML`
- `playwright`
- `Pillow`
- `aiohttp`
- `jinja2`

検索結果ページの品質評価（`content_extractor` の `evaluate_search_quality`、`search_and_validate.py`）を使う場合は、追加の依存関係（`scikit-learn`、`sentence-transformers`）が必要です。これらは容量が大きいため、通常のインストールには含まれません。

```bash
uv sync --extra quality
# 開発用ツールも含める場合
uv sync --extra dev --extra quality
# pip を利用する場合
pip install ".[quality]"
```

## 🛠️ インストールとセットアップ

1.  **Pythonの依存関係をインストール（`uv` 推奨）:**
    ```bash
    # アプリケーション実行用の依存関係を同期（.venv が自動作成されます）
    uv sync

    # テスト・Lint・型チェック等の開発用ツールも含める場合
    uv sync --extra dev
    ```
    *(従来の `pip` 環境を使う場合は、仮想環境を作成・有効化したうえで `pip install .` または `pip install -r requirements.txt` を実行してください。)*

2.  **Playwrightブラウザをインストール:**
    ```bash
    uv run playwright install
    ```

3.  **ユーザープロファイルの設定:**
    - `users/`ディレクトリ内に新しいディレクトリを作成します (例: `users/my_profile`)。実プロファイルは `.gitignore` により Git 管理対象外になります。
    - 共通設定として `users/config.yaml` を利用できます。ユーザーごとに設定を上書きしたい場合のみ、`users/my_profile/config.yaml` を作成してください。
    - `users/sample/` 内の `.sample` ファイルを新しいユーザーディレクトリへコピーし、`.sample` を外して実設定に書き換えます（`cheacker_url.json.sample` → `cheacker_url.json`、`mail.yaml.sample` → `mail.yaml`）。

    **a) `cheacker_url.json`**
    このファイルには、チェックするURLのリストが含まれています。JSONオブジェクトの配列です。新しいURLの場合、`url`のみを提供すれば十分です。ファイルが無い場合は、空の状態から作成されます。
    ```json
    [
      {"url": "https://example.com/news", "run_code": "", "result_vl": "", "updated_datetime": "", "full_scan_datetime": "", "css_selector_list": [], "web_page_type": ""},
      {"url": "https://another-site.org/updates", "run_code": "", "result_vl": "", "updated_datetime": "", "full_scan_datetime": "", "css_selector_list": [], "web_page_type": ""}
    ]
    ```

    **b) `config.yaml`（任意）**
    このファイルはアプリケーションの動作を制御します。`users/{ユーザー名}/config.yaml` がある場合はそちらを優先して読み込み、無い場合は共通の `users/config.yaml` を読み込みます。どちらも無い場合は警告ログを出力し、既定の動作（空設定）で動作します。
    ```yaml
    scan:
      worker_threads: 2       # 並列スキャン数
      timeout_per_url: 60     # 各URLスキャンのタイムアウト秒数

    notification:
      type: 'email'           # 'email' または 'none'
      notify_on_error: true   # エラー発生時にメールを送信する

    screenshot:
      enabled: true           # 通知用のスクリーンショットを有効にする
      temporary_dir: 'temp_image' # スクリーンショット用の一時フォルダ
      permanent_dir: 'data/view'  # スクリーンショットの永続的な保存場所
      email_width: 500        # メール内のスクリーンショットの幅
      permanent_width: 1920   # 保存用スクリーンショットの幅
    ```

    **c) `mail.yaml`**
    このファイルには、通知を送信するために使用されるメールアカウントの認証情報が含まれています。
    ```yaml
    gmail:
      receiver_mail: 'recipient@example.com'
      account: 'your_sender_email@gmail.com'
      password: 'your_gmail_app_password'
    ```
    *(注意: Gmailで2段階認証が有効になっている場合は、「アプリパスワード」を使用する必要があります。)*


## ▶️ 実行方法

Webチェッカーを実行するには、メインスクリプトを実行します。ユーザープロファイル名は、コマンドライン引数で指定します。省略した場合は `jav` が使われます。

```bash
python web-cheackerV3.py my_profile
```
