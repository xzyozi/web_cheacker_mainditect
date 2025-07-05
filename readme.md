以下は、今回のログ解析・スキャン判定・除外リスト保存処理に関する機能を含めた `README.md` のドラフトです。

---

# 🕵️ Web更新チェッカー（Quickスキャン / Fullスキャン対応）

## 📌 概要

本ツールは、対象Webページの更新を定期的にチェックするためのPythonスクリプトです。
Playwright による DOM 構造取得と、主要コンテンツの差分比較を行い、変更があれば通知や記録を行います。

---

## 🔍 スキャンモード

### ✅ Fullスキャン（フルスキャン）

* ページ全体の DOM 構造を取得し、主要コンテンツの候補を解析。
* 初回または selector情報が古い・失敗時に使用。
* コンテンツ選定・セレクタ取得を含むため **処理が重い**。

### ⚡ Quickスキャン（クイックスキャン）

* 前回の Fullスキャンで抽出した CSSセレクタを用い、対象領域のみ取得。
* DOM変化の影響を受けやすいが、高速処理が可能。


---

---

## 📁 ディレクトリ構成

```
project-root/
│
├─ users/                  # ユーザーごとの設定とデータ
│   └─ jav/
│       ├─ cheacker_url.csv     # 監視対象のURLとその状態
│       ├─ json/                # スキャン結果のJSON保存
│       └─ mail.yaml            # メール送信設定
│
├─ data/
│   ├─ quickscan_exclude.json  # 除外対象ドメイン一覧
│   └─ cheacker_url.csv         # （旧）全体URL情報（ユーザー移行前）
│
├─ log/
│   └─ web-chk_YYYYMMDD_HHMMSS.log  # 実行ログ
│
├─ temp_image/             # スクリーンショット一時保存
│
├─ playwright_mainditect_v3.py     # Playwright DOM抽出ロジック
├─ mail.py                         # メール送信モジュール
├─ text_struct.py                  # HTML生成ロジック
├─ dom_treeSt.py                   # DOM構造比較用クラス
├─ setup_logger.py                 # ログ設定
├─ util_str.py                     # 汎用文字列操作
└─ main.py                         # メインスクリプト
```

---

## ✅ 実行方法

```bash
python main.py
```

---

## 📤 通知機能

* 変更が検出された場合、画像付きの通知メールを送信。
* スクリーンショットは `temp_image/` に一時保存。

---

## 🔧 CSVファイル構成（cheacker\_url.csv）

| カラム名                 | 説明             |
| -------------------- | -------------- |
| url                  | 監視対象URL        |
| run\_code            | 実行日時コード        |
| result\_vl           | ハッシュ値（差分確認用）   |
| updated\_datetime    | 最終更新日時         |
| full\_scan\_datetime | 最終Fullスキャン日時   |
| css\_selector        | Quickスキャン用セレクタ |
| web\_page\_type      | 抽出されたWebページタイプ |

---

## ✉️ メール設定ファイル（`mail.yaml`）

```yaml
gmail:
  receiver_mail: example@example.com
  sender_mail: your_email@gmail.com
  password: your_password_or_app_pass
```

---

