---
title: "依存関係の管理フロー（非推奨：uv へ移行）"
document_type: "environment_setup_procedure"
document_role: "procedure"
ssot_scope: "environment"
status: "deprecated"
version: "1.1"
created_at: "2026-11-20"
updated_at: "2026-11-21"
author: "xzyozi"
owner: "xzyozi"
purpose: "旧 pip-tools 運用の廃止理由と、uv（pyproject.toml / uv.lock）による現行の依存関係管理手順への移行先を示すため"
related_documents:
  - "ドキュメントガバナンス（相対パス: ../README.md）"
  - "Python プロジェクト環境構築手順書 (uv版)（相対パス: ./python_setup.md）"
---

# 依存関係の管理フロー（非推奨：uv へ移行）

> [!WARNING]
> **非推奨 (`deprecated`)**: 本ドキュメントに記載していた `pip-tools`（`requirements.in` / `requirements.txt`）中心の依存関係管理フローは廃止され、**`uv`（`pyproject.toml` と `uv.lock`）による管理へ移行しました**。
> 現在の正規手順は [Python プロジェクト環境構築手順書 (uv版)](./python_setup.md) を参照してください。

## 廃止の理由と現行方針

- 本プロジェクトの依存関係・開発ツール・CI（`.github/workflows/ci-python.yml`、`.github/workflows/mutation-pr.yml`、`.github/workflows/mutation-nightly.yml`）は `pyproject.toml` と `uv.lock` を正本として運用しています。
- `uv.lock` は依存関係の完全な再現性を担保するため、Git の管理対象（コミット対象）としています。
- ルート直下の `requirements.in` / `requirements.txt` は旧環境との互換のために残置されていますが、新規の依存追加・環境構築には使用しません。

## 旧手順からの移行対応表

| 作業内容 | 旧手順 (`pip-tools`) | 現行手順 (`uv`) |
| :--- | :--- | :--- |
| 開発環境の構築・同期 | `python -m venv .venv` + `pip install -r requirements.txt` | `uv sync --extra dev` |
| ロックファイルの生成・更新 | `pip-compile requirements.in` | `uv lock`（または `uv sync` / `uv add`） |
| 本番依存の追加 | `requirements.in` 編集 + `pip-compile` | `uv add <package>`（または `pyproject.toml` 編集後に `uv lock`） |
| 開発用依存の追加 | — | `uv add --dev <package>` |
| 依存更新のコミット対象 | `requirements.in`, `requirements.txt` | `pyproject.toml`, `uv.lock` |

詳細な構築・検証手順は [Python プロジェクト環境構築手順書 (uv版)](./python_setup.md) を参照してください。
