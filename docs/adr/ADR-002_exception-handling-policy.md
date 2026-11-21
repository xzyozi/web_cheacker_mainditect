---
title: "ADR-002: 例外処理方針とRuff BLE/B適用基準"
document_type: "architecture_decision_record"
document_number: "ADR-002"
document_role: "rationale"
ssot_scope: "decision_rationale"
status: "accepted"
version: "1.0"
created_at: "2026-11-21"
updated_at: "2026-11-21"
author: "xzyozi"
owner: "xzyozi"
purpose: "RuffのBLE/Bルール有効化に先立ち、例外の握りつぶし可否、記録して再送出する書き方、ライブラリ別の具体例外型、および既存指摘箇所の対処方針を決定するため"
related_documents:
  - "ドキュメントガバナンス（相対パス: ../README.md）"
  - "用語集（相対パス: ../../CONTEXT.md）"
  - "ADR-001 文書ガバナンスとSSOT（相対パス: ./001-document-governance-and-ssot.md）"
  - "開発環境・ツール設定（相対パス: ../../pyproject.toml）"
---

# ADR-002: 例外処理方針とRuff BLE/B適用基準

| 項目 | 内容 |
| :--- | :--- |
| ステータス | accepted |
| 決定日 | 2026-11-21 |
| 決定者・承認者 | xzyozi |
| 置換元ADR | なし |

## 1. 背景・課題

- **背景**: コードベース全体に `except Exception`（blind except）が多数存在し、想定外のプログラムエラー（`AttributeError`、`TypeError`、`KeyError` 等）まで握りつぶして `None` や空値を返したり、`traceback.print_exc()` によってログファイルへ出力されず標準出力にのみ流れたりする箇所がある。
- **要求・制約**:
  - 定期監視のバッチ実行において、1つの URL の失敗で他 URL の監視全体が停止してはならない。
  - 一方で、内部ロジックのバグや設定不備をサイレントに隠蔽せず、原因追跡しやすい形で検知できる必要がある。
  - `pyproject.toml` の `[tool.ruff.lint] select` に `BLE`（flake8-blind-except）と `B`（flake8-bugbear）を段階的に有効化する（#47・#48）。
  - 対応 Python バージョンは `requires-python = ">=3.10"`。
- **判断しない場合の影響**: `BLE` / `B` 有効化時に各担当者が場当たり的に `# noqa: BLE001` を乱用するか、逆にバッチ境界まで例外を伝播させて監視バッチ全体を落とすリスクがある。

## 2. 決定

### 2.1 例外を握りつぶしてよい場合・いけない場合の基準

| 区分 | 方針 | 対象となる箇所・条件 | 実装ルール |
| :--- | :--- | :--- | :--- |
| **内部モジュール（原則）** | **握りつぶし禁止** | `content_extractor/` 等の抽出・解析・設定処理全般 | 起き得る具体的な例外型のみ捕捉する。`TypeError` / `AttributeError` / `KeyError` 等のプログラムバグは捕捉せず上位へ伝播させる。 |
| **ベストエフォート処理（フォールバック／解放）** | **具体例外のみ捕捉して継続可** | 失敗しても機能上の代替手段がある処理（例: `networkidle` 待機タイムアウト、非表示要素の `bounding_box` 取得失敗、一意セレクタ化の失敗時フォールバック、ページ/コンテキスト解放、テストの Chromium 起動可否判定） | 動作継続自体は妥当だが `except Exception` は使わず、起き得る具体例外型に限定したうえで `logger.debug` または `logger.warning` に記録する。 |
| **最上位バッチ境界（URL ループ境界）** | **想定外例外の捕捉を限定許容** | 複数 URL を順に処理する最上位の実行境界（例: `web-cheackerV3.py` の `process_url_async`、`search_and_validate.py` の URL ループ） | 1 URL の異常で残りの URL 監視を止めないため、具体例外を個別に扱った上で、最上位のフォールバックとして `# noqa: BLE001` ＋理由コメント付きで `Exception` を捕捉し、`logger.exception` と `error_list` 等へ記録して次の URL へ進む。`BaseException` は絶対に捕捉しない。 |

### 2.2 記録して再送出する場合の書き方

1. **原則は `logger.exception(...)` ＋引数なし `raise`**:
   - 例外の種類・メッセージ・スタックトレースをロガー（コンソールおよびファイルハンドラ）へ確実に残し、元のトレースバックを保持したまま再送出する。
2. **別例外へ変換する場合は `raise ... from e`**:
   - 依存ライブラリ未導入など呼び出し元向けの明確なエラーへ変換する場合（例: `RelevanceScorer.__init__` での `ImportError` 送出）は、`logger.error(...)` または `logger.exception(...)` 後に `raise NewError("...") from e` で原因例外を連鎖させる。
3. **`traceback.print_exc()` / `print_error_details()` の扱い**:
   - `traceback.print_exc()`（標準出力のみに出力されログファイルに残らない）の新規利用を禁止する。
   - 既存の `print_error_details(e)` および `traceback.print_exc()` 呼び出しは、#47・#48 の修正時に `logger.exception(...)` へ置き換えて整理する。

### 2.3 具体的な例外型に絞る指針

`requires-python = ">=3.10"` を前提に、領域ごとに捕捉対象を次の標準指針へ揃える。

| 領域 | 捕捉すべき代表的な例外型 | 補足・注意点 |
| :--- | :--- | :--- |
| **Playwright** | `playwright.async_api.TimeoutError`（`PlaywrightTimeoutError`）<br>`playwright.async_api.Error`（`PlaywrightError`） | `PlaywrightTimeoutError` は `PlaywrightError` のサブクラス。タイムアウトだけ別ログレベル（`warning` 等）にする場合は先に `PlaywrightTimeoutError`、続けて `PlaywrightError` を捕捉する。 |
| **aiohttp / requests** | `aiohttp.ClientError`、`asyncio.TimeoutError`<br>`requests.RequestException` | Python 3.10 では `asyncio.TimeoutError` と組み込み `TimeoutError` が別クラス（3.11 以降で統合）のため、aiohttp のタイムアウトを拾う場合は `asyncio.TimeoutError`（または `(aiohttp.ClientError, asyncio.TimeoutError)`）を明示する。 |
| **pandas / 設定・構造データ** | `pd.errors.EmptyDataError`、`pd.errors.ParserError`<br>`json.JSONDecodeError`、`yaml.YAMLError`<br>`ValueError`、`KeyError` | 入力ファイル破損や形式不備のみを捕捉する。設定値の型不整合などは安易に握りつぶさずログ記録して扱う。 |
| **ファイル I/O / 画像処理** | `OSError`（`FileNotFoundError`・`PermissionError` を含む）<br>`UnicodeDecodeError`<br>`PIL.UnidentifiedImageError` | `IOError` は Python 3 では `OSError` の別名であるため、新規・修正時は `OSError` に統一する。 |

### 2.4 `scripts/`（実験スクリプト）および `B` ルール指摘の扱い

- #48 で `per-file-ignores` をすべて撤去するため、`scripts/choice_content_experiment.py` も例外対象外とせず、他ファイルと同様に具体例外（`PlaywrightTimeoutError`, `PlaywrightError` 等）へ修正する。
- Ruff の `B` ルール（`B006` 等のバグ温床パターン）で検出された箇所も、#47・#48 の範囲で修正する。

---

## 3. 現状の blind except・Ruff `BLE/B` 指摘一覧（実測: 2026-11-21）

`uv run --no-sync ruff check --select BLE,B .` の実行結果は **合計 23 件**（`BLE001`: 22件、`B006`: 1件）。加えて、`except Exception` を記述しているが `raise ... from e` により `BLE001` 対象外となっている箇所が 1 件ある。

### 3.1 `content_extractor/` 配下（11件、#47 対象）

| # | ファイル | 行 | ルール | 対象処理と現状 | 扱い案（#47） |
| :-: | :--- | :-: | :---: | :--- | :--- |
| 1 | `content_extractor/core.py` | 237 | `BLE001` | `extract_main_content` 末尾。上で `PlaywrightTimeoutError` / `ClientError` を捕捉済みだが、残りも `None` で握りつぶし。 | 捕捉を `(PlaywrightTimeoutError, PlaywrightError, ClientError, OSError)` 等に具体化するか、想定外例外は `logger.exception` で記録して再送出（最上位 `process_url_async` に任せる）。`print_error_details` を整理。 |
| 2 | `content_extractor/core.py` | 399 | `BLE001` | `quick_extract_content` 末尾。上で `PlaywrightTimeoutError` を捕捉済みだが、残りも `None` 返し。 | 同上（`PlaywrightError` 等の既知外部エラーのみ `None`、想定外は `logger.exception` ＋再送出）。 |
| 3 | `content_extractor/make_tree.py` | 39 | `BLE001` | `parse_element` 内の `el.bounding_box()` 取得失敗をスキップ。 | `PlaywrightError` に限定してスキップ。 |
| 4 | `content_extractor/make_tree.py` | 77 | `BLE001` | `parse_element` 全体の例外を `None` で握りつぶし。 | DOM 切り離し等の `PlaywrightError` に限定し、プログラムバグは伝播。 |
| 5 | `content_extractor/make_tree.py` | 87 | `BLE001` | `page.wait_for_load_state("networkidle")` のタイムアウト等を警告して続行。 | `(PlaywrightTimeoutError, PlaywrightError)` に限定して続行。 |
| 6 | `content_extractor/make_tree.py` | 97 | `BLE001` | `make_tree` 全体の例外を `logger.critical` 後に `None` 返し。 | `PlaywrightError` に限定するか、`logger.exception` ＋再送出。 |
| 7 | `content_extractor/playwright_helpers.py` | 47 | `BLE001` | `setup_page` で `PlaywrightTimeoutError` 以外の失敗を `traceback.print_exc()` 後に `None` 返し。 | `PlaywrightError` に絞って `context` / `page` を閉じ `None` を返す（またはクリーンアップ後に想定外は再送出）。`traceback.print_exc()` は `logger.exception` へ変更。 |
| 8 | `content_extractor/playwright_helpers.py` | 110 | `BLE001` | `ensure_unique_selector` の `page.evaluate` 失敗時に元セレクタへフォールバック。 | `PlaywrightError` に限定して元セレクタを返す。 |
| 9 | `content_extractor/playwright_helpers.py` | 140 | `BLE001` | `close_page` で `page.close()` / `context.close()` 失敗を警告のみで継続。 | `PlaywrightError` に限定して警告のみで継続。 |
| 10 | `content_extractor/playwright_helpers.py` | 178 | `BLE001` | `fetch_robots_txt` で `aiohttp.ClientError` 以外の失敗を `None` 返し。 | `asyncio.TimeoutError` と `UnicodeDecodeError` 等（`(aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError)`）に具体化。 |
| 11 | `content_extractor/playwright_helpers.py` | 274 | `BLE001` | `save_screenshot` のリトライ内で `except Exception` 後に `isinstance` 分岐。 | 先に `(PlaywrightTimeoutError, OSError)` を `except` で受けてリトライし、その他の予期せぬ `PlaywrightError` / `UnidentifiedImageError` を整理。`traceback.print_exc()` を `logger.exception` に置換。 |

> **参考（`BLE001` 非検出）**: `content_extractor/relevance_scorer.py:30` は `except Exception as e:` で `logger.error` 後に `raise ImportError(...) from e` しているため `BLE001` 対象外だが、モデル読み込み失敗（`OSError`, `RuntimeError`, `ValueError` 等）を明確な `ImportError` へ変換する設計として現行維持（必要に応じて例外型を絞る）。

### 3.2 ルート・テスト・スクリプト配下（12件、#48 対象）

| # | ファイル | 行 | ルール | 対象処理と現状 | 扱い案（#48） |
| :-: | :--- | :-: | :---: | :--- | :--- |
| 12 | `web-cheackerV3.py` | 111 | `BLE001` | `User.load_app_config` で `config.yaml` 読込エラーを `{}` で握りつぶし。 | `(yaml.YAMLError, OSError, UnicodeDecodeError)` に限定。 |
| 13 | `web-cheackerV3.py` | 121 | `B006` | `User.send_resultmail` のデフォルト引数 `image_list=[]`。 | `image_list: list[str] | None = None` へ変更し内部で空リスト初期化。 |
| 14 | `web-cheackerV3.py` | 495 | `BLE001` | `process_url_async` の URL 単位処理ループ境界。`error_list` に記録し他 URL を継続。 | **バッチ境界**として `logger.exception` ＋ `error_list` 記録を維持し、`# noqa: BLE001` と理由コメントを付与。 |
| 15 | `search_and_validate.py` | 41 | `BLE001` | `search_on_google` 内の Playwright 操作失敗で `[]` を返す。 | `(PlaywrightTimeoutError, PlaywrightError)` に限定。 |
| 16 | `search_and_validate.py` | 95 | `BLE001` | `main` 内の URL 分析ループ。1件の失敗で全件を止めない。 | **バッチ境界**として具体例外捕捉＋境界なら `# noqa: BLE001` と理由コメントで記録・継続（または `PlaywrightError` 等に限定）。 |
| 17 | `test/test_integration_extract.py` | 97 | `BLE001` | テストフィクスチャ `browser()` の Chromium 起動失敗で `pytest.skip`。 | `(PlaywrightError, OSError)` に限定して `pytest.skip`。 |
| 18 | `scripts/choice_content_experiment.py` | 61 | `BLE001` | `networkidle` 待機タイムアウトの警告継続。 | `(PlaywrightTimeoutError, PlaywrightError)` に限定。 |
| 19 | `scripts/choice_content_experiment.py` | 95 | `BLE001` | `wait_for_selector` 失敗で `{}` を返す。 | `(PlaywrightTimeoutError, PlaywrightError)` に限定。 |
| 20 | `scripts/choice_content_experiment.py` | 139 | `BLE001` | `el.bounding_box()` 取得失敗をスキップ。 | `PlaywrightError` に限定。 |
| 21 | `scripts/choice_content_experiment.py` | 178 | `BLE001` | `parse_element` 内の失敗で `{}` を返す。 | `PlaywrightError` に限定。 |
| 22 | `scripts/choice_content_experiment.py` | 184 | `BLE001` | `get_tree` 全体の失敗で `{}` を返す。 | `PlaywrightError` に限定。 |
| 23 | `scripts/choice_content_experiment.py` | 294 | `BLE001` | `choice_content` 内で `traceback.print_exc()` 後に `{}` を返す。 | `(PlaywrightTimeoutError, PlaywrightError)` に限定し `logging.exception` を使用。 |

---

## 4. 理由・代替案

### 採用理由

1. 内部モジュールでは具体例外型に絞ることで、DOM 構造やリファクタリングに起因する `AttributeError` / `TypeError` 等のバグを即座に検知できる。
2. 最上位の URL バッチ境界に限って `# noqa: BLE001`（理由コメント必須）と `logger.exception` を許容することで、「1サイトの異常で他サイトの監視が止まらない」運用要件と静的解析の両立ができる。
3. ライブラリ別の標準例外マップを先に合意しておくことで、#47・#48 の修正時の判断ブレを防げる。

### 代替案

| 代替案 | 利点 | 欠点・リスク | 採用しなかった理由 |
| :--- | :--- | :--- | :--- |
| `# noqa: BLE001` を一切禁止し、全箇所を具体例外のみにする | ルールが単純で例外規定が不要 | 予期しない1件の URL の不具合で定期バッチ全体が途中終了する恐れがある | バッチ監視の継続性を損なうため採用しない |
| 既存の `except Exception` をそのまま維持し、`BLE` を有効化しない | 改修コストゼロ | プログラム上のバグや設定誤りが静かに `None` / `{}` になり原因特定が困難になる | Issue #27 / #46 の目的に反するため採用しない |

## 5. 影響・トレードオフ

- **利点**: バグのサイレント握りつぶしを防ぎつつ、ログファイル（`logger.exception`）でスタックトレースを追跡できる。
- **欠点・コスト**: `PlaywrightError` や `asyncio.TimeoutError` 等の例外クラス把握と、#47・#48 での振る舞い変更箇所に対する単体テスト追加の工数が発生する。
- **影響を受ける正本文書**: `pyproject.toml`（#47・#48 での `select` / `per-file-ignores` 更新）、実装コードおよび関連テスト。
- **移行・ロールバック**: コードの振る舞いを変える修正は #47・#48 に分離しているため、本 ADR 自体は方針決定のみ。変更時は本 ADR を `superseded` として後継 ADR を作成する。

## 6. 関連文書・後続作業

- **要求・Issue**:
  - Issue #46: `[docs] 例外処理の方針を決める（ADR）`
  - 元の Issue: #27（保守性）
- **実装・検証タスク**:
  - [ ] Issue #47: `ruff` の `BLE`/`B` を有効化し、`content_extractor/` の例外処理を本 ADR に沿って修正する
  - [ ] Issue #48: ルートのスクリプト・テスト・`scripts/` に `BLE`/`B` を適用し、一時的な `per-file-ignores` をすべて外す
- **後続ADR**: なし

## 7. 例外・見直し条件

- **例外・適用差異**: 最上位バッチ境界以外の箇所でやむを得ず `Exception` を捕捉する必要がある場合は、`# noqa: BLE001` とともに「捕捉が必要な理由」と「再送出しない場合の安全根拠」をコードコメントに記載する。
- **見直し条件**: Python 最小サポートバージョンを 3.11 以上へ引き上げた場合（`asyncio.TimeoutError` と `TimeoutError` の統合）、またはバッチ実行アーキテクチャを変更した場合に見直す。
- **見直し時期**: 次の Python バージョン引き上げ時。

## 8. 作成完了チェック

- [x] この判断がADRを必要とする重要度か確認した。
- [x] 背景、決定、理由、代替案、影響を記入した。
- [x] 現在の仕様を定義する正本文書・関連文書へのリンクを設定した。
- [x] 判断変更時は本書を削除せず、後継ADRを作成する方針を確認した。
- [x] 機密情報や認証情報を記載していない。

## 9. 改訂履歴 (Change Log)

| 版数 | 改訂日 | 変更者 | 変更内容・変更理由 (Why) |
| :--- | :--- | :--- | :--- |
| Rev.1.0 | 2026-11-21 | xzyozi | 新規作成（Issue #46 例外処理方針の策定） |
