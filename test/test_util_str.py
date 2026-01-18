import pytest
from unittest.mock import patch, mock_open
from util_str import get_domain, util_handle_path
import os

# =================================================================
# util_str.py のテスト
# =================================================================

# --- Tests for get_domain ---

@pytest.mark.parametrize("url, expected_domain", [
    ("http://example.com/path", "example.com"),
    ("https://www.google.com/search?q=pytest", "www.google.com"),
    ("ftp://files.example.org", "files.example.org"),
    ("http://localhost:8000", "localhost:8000"),
])
def test_get_domain(url, expected_domain):
    assert get_domain(url) == expected_domain

# --- Tests for util_handle_path ---

def test_util_handle_path_creates_file_with_extension(mocker):
    """Test creating a file when path has an extension."""
    mocker.patch('os.path.isfile', return_value=False)
    mock_makedirs = mocker.patch('os.makedirs')
    mock_chmod = mocker.patch('os.chmod')
    
    with patch('builtins.open', mock_open()) as mocked_file:
        result = util_handle_path('some/dir/file.txt')
        
        mock_makedirs.assert_called_once_with('some/dir', exist_ok=True)
        mocked_file.assert_called_once_with('some/dir/file.txt', 'w')
        mock_chmod.assert_called_once_with('some/dir/file.txt', 0o755)
        assert result == 'some/dir/file.txt'

def test_util_handle_path_creates_directory(mocker):
    """Test creating a directory when path has no extension and no custom filename."""
    mocker.patch('os.path.isdir', return_value=False)
    mock_makedirs = mocker.patch('os.makedirs')
    mock_chmod = mocker.patch('os.chmod')
    
    result = util_handle_path('some/dir/subdir')
    
    mock_makedirs.assert_called_once_with('some/dir/subdir')
    mock_chmod.assert_called_once_with('some/dir/subdir', 0o755)
    assert result == 'some/dir/subdir'

def test_util_handle_path_creates_file_with_custom_name(mocker):
    """Test creating a file with a custom name when path has no extension."""
    mocker.patch('os.path.isfile', return_value=False)
    mock_makedirs = mocker.patch('os.makedirs')
    mock_chmod = mocker.patch('os.chmod')

    with patch('builtins.open', mock_open()) as mocked_file:
        # The path is 'some/dir/subdir', so os.path.split gives ('some/dir', 'subdir')
        # The function then joins 'some/dir' with 'custom.log'
        result = util_handle_path('some/dir/subdir', custom_filename='custom.log')
        
        expected_path = os.path.join('some/dir', 'custom.log')
        mock_makedirs.assert_called_once_with('some/dir', exist_ok=True)
        mocked_file.assert_called_once_with(expected_path, 'w')
        mock_chmod.assert_called_once_with(expected_path, 0o755)
        assert result == expected_path

def test_util_handle_path_file_already_exists(mocker):
    """Test behavior when the file to be created already exists."""
    mocker.patch('os.path.isfile', return_value=True)
    mock_makedirs = mocker.patch('os.makedirs')
    mock_chmod = mocker.patch('os.chmod')
    
    with patch('builtins.open', mock_open()) as mocked_file:
        result = util_handle_path('some/dir/file.txt')
        
        mock_makedirs.assert_not_called()
        mocked_file.assert_not_called()
        mock_chmod.assert_not_called()
        assert result == 'some/dir/file.txt'

def test_util_handle_path_directory_already_exists(mocker):
    """Test behavior when the directory to be created already exists."""
    mocker.patch('os.path.isdir', return_value=True)
    mock_makedirs = mocker.patch('os.makedirs')
    mock_chmod = mocker.patch('os.chmod')
    
    result = util_handle_path('some/dir/subdir')
    
    mock_makedirs.assert_not_called()
    mock_chmod.assert_not_called()
    assert result == 'some/dir/subdir'