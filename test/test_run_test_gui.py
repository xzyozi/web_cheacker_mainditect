"""test/run_test_gui.py のコマンド組み立てと CLI モジュール起動のテスト。"""

import importlib.util
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_run_test_gui_module():
    """std の `test` パッケージとの名前衝突を避けて `test/run_test_gui.py` を読み込む。"""
    module_path = PROJECT_ROOT / "test" / "run_test_gui.py"
    spec = importlib.util.spec_from_file_location("run_test_gui_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_test_gui_module():
    return _load_run_test_gui_module()


def test_build_command_full_mode(run_test_gui_module):
    """full モードでは -m content_extractor.core と --mode full が使われる。"""
    case = {
        "name": "Example Full",
        "url": "https://example.com/",
        "mode": "full",
        "selector": "div#ignored",
    }
    cmd = run_test_gui_module.build_command(case)

    assert cmd == [
        sys.executable,
        "-m",
        "content_extractor.core",
        "https://example.com/",
        "--mode",
        "full",
    ]
    assert "--selector" not in cmd
    assert "--selectors" not in cmd


def test_build_command_quick_mode_with_selector(run_test_gui_module):
    """quick モードでセレクタ指定ありの場合 --selectors が使われる。"""
    case = {
        "name": "Example Quick",
        "url": "https://example.com/article",
        "mode": "quick",
        "selector": "div#article-body[id='article-body']",
    }
    cmd = run_test_gui_module.build_command(case)

    assert cmd == [
        sys.executable,
        "-m",
        "content_extractor.core",
        "https://example.com/article",
        "--mode",
        "quick",
        "--selectors",
        "div#article-body[id='article-body']",
    ]
    assert "--selector" not in cmd


@pytest.mark.parametrize(
    "case",
    [
        {"name": "Empty selector", "url": "https://example.com/", "mode": "quick", "selector": ""},
        {"name": "Missing selector", "url": "https://example.com/", "mode": "quick"},
    ],
)
def test_build_command_quick_mode_without_selector(run_test_gui_module, case):
    """quick モードでセレクタが空または未指定の場合 --selectors は付与されない。"""
    cmd = run_test_gui_module.build_command(case)

    assert cmd == [
        sys.executable,
        "-m",
        "content_extractor.core",
        "https://example.com/",
        "--mode",
        "quick",
    ]
    assert "--selectors" not in cmd


def test_execute_subprocess_uses_module_cli_and_project_root_cwd(run_test_gui_module):
    """_execute_subprocess が組み立てたコマンドと project_root の cwd で Popen を呼ぶ。"""
    app = run_test_gui_module.TestRunnerApp.__new__(run_test_gui_module.TestRunnerApp)
    app.project_root = str(PROJECT_ROOT)
    app.root = MagicMock()

    mock_proc = MagicMock()
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline.side_effect = ["ok\n", ""]

    case = {
        "name": "Quick Case",
        "url": "https://example.com/",
        "mode": "quick",
        "selector": "main.content",
    }

    with patch.object(run_test_gui_module.subprocess, "Popen", return_value=mock_proc) as mock_popen:
        app._execute_subprocess(case)

    mock_popen.assert_called_once()
    called_args, called_kwargs = mock_popen.call_args
    assert called_args[0] == [
        sys.executable,
        "-m",
        "content_extractor.core",
        "https://example.com/",
        "--mode",
        "quick",
        "--selectors",
        "main.content",
    ]
    assert called_kwargs["cwd"] == str(PROJECT_ROOT)
    mock_proc.wait.assert_called_once()


def test_content_extractor_core_module_help_exits_zero():
    """`python -m content_extractor.core --help` が終了コード 0 でヘルプを出力する。"""
    result = subprocess.run(
        [sys.executable, "-m", "content_extractor.core", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "--mode" in result.stdout
    assert "--selectors" in result.stdout
