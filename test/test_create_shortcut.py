from pathlib import Path

import pytest

import create_shortcut


def test_bat_content_has_no_control_characters() -> None:
    """BAT_CONTENT にベル文字 (\\x07) などの制御文字が混入していないことを確認する。"""
    assert "\x07" not in create_shortcut.BAT_CONTENT
    unexpected_control_chars = [
        ch for ch in create_shortcut.BAT_CONTENT if (ord(ch) < 0x20 and ch not in ("\n", "\r", "\t")) or ord(ch) == 0x7F
    ]
    assert unexpected_control_chars == []


def test_bat_content_contains_expected_windows_paths() -> None:
    """BAT_CONTENT の Windows パスが単一のバックスラッシュで正しく出力されることを確認する。"""
    assert r'if exist ".venv\Scripts\activate.bat" (' in create_shortcut.BAT_CONTENT
    assert r"    call .venv\Scripts\activate.bat" in create_shortcut.BAT_CONTENT
    assert r"WARNING: Virtual environment not found at .\.venv\ ." in create_shortcut.BAT_CONTENT
    assert "python web-cheackerV3.py" in create_shortcut.BAT_CONTENT


def test_create_shortcut_writes_valid_bat_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """create_shortcut() が生成する .bat ファイルに制御文字がなく期待通りの内容であることを確認する。"""
    monkeypatch.chdir(tmp_path)

    create_shortcut.create_shortcut()

    bat_path = tmp_path / create_shortcut.FILE_NAME
    assert bat_path.is_file()
    content = bat_path.read_text(encoding="utf-8")
    assert content == create_shortcut.BAT_CONTENT
    assert "\x07" not in content
    assert r".venv\Scripts\activate.bat" in content
