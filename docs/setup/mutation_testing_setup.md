---
title: "ミューテーションテスト導入・運用ガイド (mutmut v3)"
document_type: "environment_setup_procedure"
document_role: "procedure"
ssot_scope: "environment"
status: "approved"
version: "1.0"
created_at: "2026-11-19"
updated_at: "2026-11-19"
author: "Template Maintainer"
owner: "Template Maintainer"
purpose: "Pythonプロジェクトにおいて mutmut v3 と GitHub Actions の2段構成（PR差分・Nightly全件）を低ノイズかつ高速に導入・運用する手順を定義するため"
related_documents:
  - "ドキュメントガバナンス（相対パス: ../README.md）"
  - "用語集（相対パス: ../../CONTEXT.md）"
  - "Python プロジェクト環境構築手順書（相対パス: ./python_setup.md）"
  - "環境・開発基盤仕様書テンプレート（相対パス: ./TEMPLATE/TEMPLATE_環境・開発基盤仕様書.md）"
---

# ミューテーションテスト導入・運用ガイド (`mutmut` v3)

本ガイドは、Python プロジェクトのテスト品質を低コストで計測するため、`mutmut` v3 と GitHub Actions（PR 差分実行 ＋ Nightly 全件実行）を導入・運用する標準手順を定義する。

---

## 1. 設計思想

ミューテーションテストを実務で破綻させないため、以下の原則を採用する。

| 原則 | `mutmut` v3 / CI での実現方法 |
| :--- | :--- |
| **純粋ロジックに絞る** | `only_mutate` / `do_not_mutate` でドメイン・計算層に限定し、I/O や薄いラッパーを除外する |
| **高速テストだけ回す** | `pytest_add_cli_args_test_selection` でユニットテストに限定し、`max_stack_depth` で間接通過テストを除外する |
| **型エラー変異を事前除外** | `type_check_command` に `mypy`（または `pyrefly`）を指定し、テスト前に無意味なミュータントを間引く |
| **未カバー行のノイズ削減** | `mutate_only_covered_lines = true` で `coverage.py` が通った行だけを対象化する |
| **キャッシュと2段実行** | `mutants/` を CI キャッシュで引き継ぎ、PR は差分実行、Nightly は全件計測・可視化に分離する |
| **初期はゲートにしない** | 初期は Step Summary と Artifact による指標可視化に留め、等価ミュータントで開発を止めない |

---

## 2. 構成ファイルと前提条件

### テンプレートに同梱される構成

- `pyproject.toml`: `[project.optional-dependencies]` の `dev` / `mutation` 定義と、コメントアウト済みの `[tool.mutmut]` 雛形
- `.gitignore`: `mutants/`、`.coverage`、`.coverage.*` の除外設定
- `.github/workflows/mutation-pr.yml`: PR 向けの差分・インクリメンタル実行ワークフロー（opt-in）
- `.github/workflows/mutation-nightly.yml`: 毎日 JST 03:00 の全件実行・統計出力ワークフロー（opt-in）

### 動作制約

- **OS 制約**: `mutmut` v3 は `os.fork` に依存するため、実行環境は **Linux 必須**（CI は `ubuntu-latest` 固定）。Windows ローカルでは直接実行できないため、後述の WSL2 / DevContainer または CI 出力連携を利用する。
- **Opt-in 契約**: テンプレート初期状態や非 Python プロジェクトで CI が失敗しないよう、ワークフローは **`pyproject.toml` に有効な `[tool.mutmut]` セクションがあり、かつ `uv.lock` が存在する** 場合のみ実行される。

---

## 3. 有効化手順（Opt-in）

### ステップ 1: `pyproject.toml` を設定する

1. `pyproject.toml` 末尾の `# [tool.mutmut]` ブロックのコメントアウトを解除する。
2. プロジェクトのディレクトリ構成に合わせて以下を調整する。
   - `source_paths`: `["src/"]` または `["app/"]`
   - `only_mutate`: I/O を含まない純粋ロジック・重要ドメインのパスに限定する
   - `pytest_add_cli_args_test_selection`: 高速なユニットテストのディレクトリ・マーカーを指定する
   - `type_check_command`: `mypy` の対象パス（`src` または `app`）を `source_paths` に合わせる

### ステップ 2: ロックファイル更新と依存同期

```bash
# ロックファイル更新（CI の --frozen 同期およびキャッシュキーに利用）
uv lock

# 日常開発（Windows / macOS / Linux 共通）
uv sync --extra dev

# ミューテーションテスト実行環境（Linux / WSL2 / CI）
uv sync --extra dev --extra mutation
```

### ステップ 3: 初回スモークテスト（インポートパス誤検知の防止）

`mutmut` v3 はソースコードを `mutants/` にコピーしてテストを実行する。editable install や特殊な `PYTHONPATH` 設定により、テストが `mutants/` ではなく元の無変異コードを参照してしまうと、すべて `Survived` になるサイレントな誤検知が起きる。

初回導入時は以下を必ず確認する（Linux / WSL2 環境または PR 上で実施）。

1. `only_mutate` 配下の純粋関数を 1 箇所だけテスト可能な形で対象にする。
2. 対象モジュールに対して `uv run mutmut run "my_app.domain.target.*"` を実行する。
3. 既存テストが正常にミュータントを検出し、`Killed` が 1 件以上カウントされることを確認する。

---

## 4. CI ワークフローの動作仕様

### PR CI（`.github/workflows/mutation-pr.yml`）

- **実行契機**: `main` / `develop` 向け PR で `src/**/*.py`、`app/**/*.py`、`tests/**/*.py`、`pyproject.toml`、`uv.lock` が変更されたとき（および手動実行）。
- **実行モードの自動切替**:
  - `src/` または `app/` に追加・変更・リネーム（`--diff-filter=ACMR`）がある場合：変更モジュールのみを `module.*` パターンで差分実行（`set -f` でシェル glob 展開を抑止）。
  - ソース変更がなく `tests/` や設定のみ変更された場合：キャッシュを復元して引数なし実行（`mutmut` v3 のインクリメンタル実行）を行い、テスト追加による Survived 解消を検証する。
- **キャッシュ**: `mutmut-pr-<ref>-<uv.lockハッシュ>-<github.sha>` をキーとし、同一 PR 内の再 push でも最新 `mutants/` を保存する。未ヒット時は `main` の Nightly キャッシュへフォールバックする。
- **成果物**: GitHub Step Summary に結果一覧を出力し、Artifact（`mutation-pr-report`）へ `mutation-results.txt` と Survived 上位 20 件の差分（`mutation-survived-diffs.txt`）を保存する。

### Nightly CI（`.github/workflows/mutation-nightly.yml`）

- **実行契機**: 毎日 UTC 18:00（JST 03:00）および `workflow_dispatch`。
- **処理内容**: 全件実行して `main` キャッシュを最新化し、`mutmut export-cicd-stats` と `mutmut badge --output mutation-score.json` を実行する。
- **成果物**: Artifact（`mutation-nightly-stats`）へスコア JSON・CI/CD 統計・結果一覧・Survived 上位 50 件の差分を保存する。

---

## 5. 品質ゲート（`QG-xxx`）と実務ルール

### 品質ゲートにおける位置づけ

- 環境・開発基盤仕様書（`TEMPLATE_環境・開発基盤仕様書.md` の 4.4）で品質ゲートを定義する際、ミューテーションテストは **初期段階ではマージ必須のハードゲートに含めず、継続的な品質指標（情報提供 / Nightly 監視）** として扱う。
- 将来的にゲート化する場合も、全コード一律ではなく重要ドメイン層に限定し、現実的なスコア閾値（例: 75〜85%）を設定する。

### 等価ミュータントとノイズの扱い

- **正当な Survived はプラグマで閉じる**: 振る舞いが変わらない等価ミュータントや意図的な最適化には `# pragma: no mutate`（単一行）または `# pragma: no mutate block`（ブロック単位）を明示的に付与する。
- **デッドコードの検出に活かす**: 消しても・変異させてもテストが落ちない分岐は、まず不要コードや仕様漏れを疑い、テスト追加だけでなくリファクタリング対象として検討する。
- **`do_not_mutate_patterns` の段階導入**: 初期設定では `logger\.\w+` のみ除外する。`raise \w+` のような例外行の一律除外は、例外型検証が甘いテスト（例: `pytest.raises(Exception)`）の見逃しにつながるため、実際にノイズが顕著な場合のみ個別検討する。

---

## 6. Windows 環境での運用と AI エージェント連携

Windows ネイティブ環境では `mutmut` v3 が動作しないため、以下のいずれかで運用する。

1. **CI 出力を AI エージェントへ渡す（推奨・環境構築不要）**
   - PR CI / Nightly CI が出力した Artifact の `mutation-survived-diffs.txt`（または Step Summary）を取得し、AI エージェントへ渡して「この Survived を検出する境界値テストを追加し、不要な分岐であれば削除する」修正ループを回す。
2. **WSL2 / DevContainer でローカル実行する**
   - Linux 環境上で `uv sync --extra dev --extra mutation` を実行し、`uv run mutmut run` / `uv run mutmut results` / `uv run mutmut show <mutant_name>` を直接実行する。
