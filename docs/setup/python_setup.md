---
title: "Python プロジェクト環境構築手順書 (uv版)"
document_type: "environment_setup_procedure"
document_role: "procedure"
ssot_scope: "environment"
status: "draft"
version: "1.0"
created_at: "2026-11-15"
updated_at: "2026-11-15"
author: "xzyozi"
owner: "xzyozi"
purpose: "uv を利用した Python 開発環境の立ち上げおよび汎用 CI 連携の手順を定義するため"
related_documents:
  - "ドキュメントガバナンス（相対パス: ../README.md）"
  - "Git Flow 運用規約 ＆ ブランチ自動管理ガイド（相対パス: ./git_flow_and_branch_policy.md）"
---

# Python プロジェクト環境構築手順書 (uv版)

本ドキュメントは、`uv` を用いて新規 Python プロジェクトを初期化・環境構築し、汎用 CI（`.github/workflows/ci-python.yml`）を稼働させるための標準手順を定めます。

---

## 1. 目的・対象範囲

- **目的**: 統一された品質ガードレール（Ruff / Mypy / Pytest）を持つモダンで高速な Python 開発環境の迅速な立ち上げ。
- **対象環境**: ローカル開発環境（macOS / Linux / Windows）および GitHub Actions 実行環境。
- **対象者**: プロジェクト開発者、保守担当者。
- **対象外**: Python 自体のインストール手順（Python 3.10 以上の利用を前提とする）。

---

## 2. 前提条件

- **ランタイム**: Python 3.10 以上（推奨: 3.12）
- **パッケージマネージャ**: [uv](https://docs.astral.sh/uv/)（推奨: 最新版）
- **初期資材**: リポジトリ直下の `pyproject.toml`, `.python-version`

---

## 3. 構築手順

### 手順 1: uv のインストール

未導入の場合は、公式スクリプトまたは各 OS のパッケージマネージャで `uv` をインストールします。

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 手順 2: 依存関係の同期（仮想環境の自動構築）

リポジトリのルートディレクトリで以下のコマンドを実行します。`.venv` の作成と開発用依存パッケージのインストールが自動的に行われます。

```bash
uv sync --extra dev
```

実行後、`uv.lock` が生成・更新されます。**`uv.lock` は依存関係の完全な再現性を保つため、必ず Git にコミットしてください**。

### 手順 3: プロジェクト名の設定

`pyproject.toml` の `[project]` セクションにある `name` および `description` を対象プロジェクトに合わせて更新します。

```toml
[project]
name = "your-project-name"
version = "0.1.0"
description = "Project description"
```

### 手順 4: ライブラリの追加・削除

ライブラリを追加する際は、直接 `pyproject.toml` を編集するほか、`uv` コマンドを使用できます。

```bash
# 本番依存の追加
uv add requests

# 開発用依存の追加
uv add --dev pytest-mock
```

---

## 4. 構築後の確認（ローカル検証）

以下の 4 コマンドを実行し、すべて正常終了（エラー 0 件）することを確認します。

| 確認項目 | 実行コマンド | 期待結果 |
| :--- | :--- | :--- |
| **Lint 検査** | `uv run --no-sync ruff check .` | 指摘ゼロで終了すること |
| **Format 検査** | `uv run --no-sync ruff format --check .` | フォーマット差分なしで終了すること |
| **型検査** | `uv run --no-sync mypy .` | 型エラーなしで終了すること |
| **単体テスト** | `uv run --no-sync pytest` | テストが全件パスすること |

---

## 5. CI/CD 連携仕様

- ルートディレクトリに `pyproject.toml` が配置されている場合、`.github/workflows/ci-python.yml` が自動的に有効化されます。
- `push` および `pull_request` イベント（対象ブランチ: `main`, `develop`）時に、上記の 4 ステップが自動検証されます。
- `pyproject.toml` が存在しない環境（TypeScript 専用リポジトリ等）では、Python 関連ステップが自動的にスキップされ、不要なエラーは発生しません。
- 初期状態でテストが 0 件の場合でも、CI が失敗しないよう安全制御が組み込まれています。
