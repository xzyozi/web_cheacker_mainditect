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
│   └─ {ユーザー名}/        # ユーザーディレクトリの例 (例: 'jav')
│       ├─ cheacker_url.jsonl # 監視対象URLとその状態のリスト (JSON Lines形式)
│       ├─ config.yaml        # このユーザー用のメインアプリケーション設定
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
├─ requirements.txt        # プロジェクトの依存関係 (この名前を想定)
└─ readme.md               # このファイル
```

## ⚙️ 要件

このプロジェクトにはPython 3.8以上が必要です。必要なライブラリは`requirements.txt`からインストールできます。

**主な依存関係:**
- `pandas`
- `PyYAML`
- `playwright`
- `Pillow`
- `aiohttp`
- `jinja2`

`high_precision_search_system.py`スクリプトには、`requirements_search.txt`に記載されている別の依存関係があります。

## 🛠️ インストールとセットアップ

1.  **Pythonの依存関係をインストール:**
    ```bash
    # 最初に仮想環境を作成することをお勧めします
    pip install -r requirements.txt 
    ```
    *(注意: 完全な`requirements.txt`が存在しない場合は、生成する必要があるかもしれません。)*

2.  **Playwrightブラウザをインストール:**
    ```bash
    playwright install
    ```

3.  **ユーザープロファイルの設定:**
    - `users/`ディレクトリ内に新しいディレクトリを作成します (例: `users/my_profile`)。
    - 新しいユーザーディレクトリ内に、以下の3つのファイルを作成します。

    **a) `cheacker_url.jsonl`**
    このファイルには、チェックするURLのリストが含まれています。各行はJSONオブジェクトです。新しいURLの場合、`url`のみを提供すれば十分です。
    ```json
    {"url": "https://example.com/news", "run_code": "", "result_vl": "", "updated_datetime": "", "full_scan_datetime": "", "css_selector_list": [], "web_page_type": ""}
    {"url": "https://another-site.org/updates", "run_code": "", "result_vl": "", "updated_datetime": "", "full_scan_datetime": "", "css_selector_list": [], "web_page_type": ""}
    ```

    **b) `config.yaml`**
    このファイルはアプリケーションの動作を制御します。
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

Webチェッカーを実行するには、メインスクリプトを実行します。`web-cheackerV3.py`内の`User()`オブジェクトのインスタンス化を、ご自身のユーザープロファイルディレクトリ名を指すように変更する必要があります。

`web-cheackerV3.py`内:
```python
# "jav" をあなたのプロファイルディレクトリ名に変更してください
user = User("jav") 
```

その後、`main`ディレクトリからスクリプトを実行します:
```bash
python web-cheackerV3.py
```
