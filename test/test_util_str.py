import logging
import os
import stat
from unittest.mock import mock_open, patch

import pytest

from utils.util_str import ensure_dir, ensure_file, get_domain, sanitize_filename_part, util_handle_path

# =================================================================
# util_str.py のテスト
# =================================================================

# --- Tests for get_domain / sanitize_filename_part ---


@pytest.mark.parametrize(
    "url, expected_domain",
    [
        ("http://example.com/path", "example.com"),
        ("https://www.google.com/search?q=pytest", "www.google.com"),
        ("ftp://files.example.org", "files.example.org"),
        ("http://localhost:8000", "localhost:8000"),
    ],
)
def test_get_domain(url, expected_domain):
    assert get_domain(url) == expected_domain


@pytest.mark.parametrize(
    "raw_value, expected",
    [
        ("example.com", "example.com"),
        ("localhost:8000", "localhost_8000"),
        ("127.0.0.1:8080", "127.0.0.1_8080"),
        ('a<b>c:d/e\\f|g?h*i"j', "a_b_c_d_e_f_g_h_i_j"),
    ],
)
def test_sanitize_filename_part(raw_value, expected):
    assert sanitize_filename_part(raw_value) == expected


# --- Tests for util_handle_path ---


def test_util_handle_path_creates_file_with_extension(mocker):
    """Test creating a file when path has an extension."""
    mocker.patch("os.path.isfile", return_value=False)
    mock_makedirs = mocker.patch("os.makedirs")
    mock_chmod = mocker.patch("os.chmod")

    with patch("builtins.open", mock_open()) as mocked_file:
        result = util_handle_path("some/dir/file.txt")

        mock_makedirs.assert_called_once_with("some/dir", exist_ok=True)
        mocked_file.assert_called_once_with("some/dir/file.txt", "w", encoding="utf-8")
        mock_chmod.assert_not_called()
        assert result == "some/dir/file.txt"


def test_util_handle_path_creates_directory(mocker):
    """Test creating a directory when path has no extension and no custom filename."""
    mocker.patch("os.path.isdir", return_value=False)
    mock_makedirs = mocker.patch("os.makedirs")
    mock_chmod = mocker.patch("os.chmod")

    result = util_handle_path("some/dir/subdir")

    mock_makedirs.assert_called_once_with("some/dir/subdir", exist_ok=True)
    mock_chmod.assert_not_called()
    assert result == "some/dir/subdir"


def test_util_handle_path_creates_file_with_custom_name(mocker):
    """Test creating a file with a custom name when path has no extension."""
    mocker.patch("os.path.isfile", return_value=False)
    mock_makedirs = mocker.patch("os.makedirs")
    mock_chmod = mocker.patch("os.chmod")

    with patch("builtins.open", mock_open()) as mocked_file:
        # The path is 'some/dir/subdir', so os.path.split gives ('some/dir', 'subdir')
        # The function then joins 'some/dir' with 'custom.log'
        result = util_handle_path("some/dir/subdir", custom_filename="custom.log")

        expected_path = os.path.join("some/dir", "custom.log")
        mock_makedirs.assert_called_once_with("some/dir", exist_ok=True)
        mocked_file.assert_called_once_with(expected_path, "w", encoding="utf-8")
        mock_chmod.assert_not_called()
        assert result == expected_path


def test_util_handle_path_file_already_exists(mocker):
    """Test behavior when the file to be created already exists."""
    mocker.patch("os.path.isfile", return_value=True)
    mock_makedirs = mocker.patch("os.makedirs")
    mock_chmod = mocker.patch("os.chmod")

    with patch("builtins.open", mock_open()) as mocked_file:
        result = util_handle_path("some/dir/file.txt")

        mock_makedirs.assert_not_called()
        mocked_file.assert_not_called()
        mock_chmod.assert_not_called()
        assert result == "some/dir/file.txt"


def test_util_handle_path_directory_already_exists(mocker):
    """Test behavior when the directory to be created already exists."""
    mocker.patch("os.path.isdir", return_value=True)
    mock_makedirs = mocker.patch("os.makedirs")
    mock_chmod = mocker.patch("os.chmod")

    result = util_handle_path("some/dir/subdir")

    mock_makedirs.assert_not_called()
    mock_chmod.assert_not_called()
    assert result == "some/dir/subdir"


def test_util_handle_path_trailing_slash_with_dot_creates_directory(tmp_path):
    """末尾スラッシュ付きでドットを含むパスでもディレクトリとして作成される。"""
    target_dir = f"{tmp_path / 'v1.0'}/"
    result = util_handle_path(target_dir)

    assert result == target_dir
    assert os.path.isdir(target_dir)
    assert not os.path.isfile(str(tmp_path / "v1.0"))


# --- Tests for ensure_file / ensure_dir ---


def test_ensure_file_without_parent_directory_and_no_exec_bit(tmp_path, monkeypatch):
    """親ディレクトリ省略パスでも FileNotFoundError にならず、実行権限も付けない。"""
    monkeypatch.chdir(tmp_path)
    result = ensure_file("plain.txt")

    assert result == "plain.txt"
    created = tmp_path / "plain.txt"
    assert created.is_file()
    assert created.read_text(encoding="utf-8") == ""
    assert (created.stat().st_mode & stat.S_IXUSR) == 0


def test_ensure_file_returns_none_and_logs_on_os_error(mocker, caplog):
    """ファイル作成時の OSError ではエラーログを出して None を返す。"""
    mocker.patch("os.path.isfile", return_value=False)
    mocker.patch("os.makedirs", side_effect=OSError("permission denied"))

    with caplog.at_level(logging.ERROR, logger="utils.util_str"):
        result = ensure_file("restricted/file.txt")

    assert result is None
    assert any("作成できませんでした" in rec.message for rec in caplog.records)


def test_ensure_dir_returns_none_and_logs_on_os_error(mocker, caplog):
    """ディレクトリ作成時の OSError ではエラーログを出して None を返す。"""
    mocker.patch("os.path.isdir", return_value=False)
    mocker.patch("os.makedirs", side_effect=OSError("disk full"))

    with caplog.at_level(logging.ERROR, logger="utils.util_str"):
        result = ensure_dir("restricted/dir")

    assert result is None
    assert any("作成できませんでした" in rec.message for rec in caplog.records)
