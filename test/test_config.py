import pytest
import json
import os
from unittest.mock import patch, mock_open

from content_extractor.config import _load_json_config

# =================================================================
# config.py のテスト
# =================================================================

DEFAULT_CONFIG = {"key": "default_value"}
CUSTOM_CONFIG = {"key": "custom_value"}

@patch("os.path.abspath")
@patch("os.path.dirname")
def test_load_json_config_success(mock_dirname, mock_abspath):
    """Test Case 1: Successfully loads a JSON config file."""
    mock_abspath.return_value = "/fake/path/content_extractor/config.py"
    mock_dirname.return_value = "/fake/path/content_extractor"
    
    # Simulate the file exists and contains valid JSON
    m = mock_open(read_data=json.dumps(CUSTOM_CONFIG))
    with patch("builtins.open", m):
        config = _load_json_config("config.json", DEFAULT_CONFIG)
        assert config == CUSTOM_CONFIG
        expected_path = os.path.join("/fake/path/content_extractor", 'config', 'config.json')
        m.assert_called_once_with(expected_path, 'r', encoding='utf-8')

@patch("os.path.abspath")
@patch("os.path.dirname")
def test_load_json_config_file_not_found(mock_dirname, mock_abspath):
    """Test Case 2: Config file not found, returns default."""
    mock_abspath.return_value = "/fake/path/content_extractor/config.py"
    mock_dirname.return_value = "/fake/path/content_extractor"
    
    # Simulate a FileNotFoundError
    with patch("builtins.open", mock_open()) as m:
        m.side_effect = FileNotFoundError
        config = _load_json_config("config.json", DEFAULT_CONFIG)
        assert config == DEFAULT_CONFIG

@patch("os.path.abspath")
@patch("os.path.dirname")
def test_load_json_config_invalid_json(mock_dirname, mock_abspath):
    """Test Case 3: Invalid JSON in config file, returns default."""
    mock_abspath.return_value = "/fake/path/content_extractor/config.py"
    mock_dirname.return_value = "/fake/path/content_extractor"
    
    # Simulate the file exists but contains invalid JSON
    m = mock_open(read_data="{ 'key': 'invalid_json' }") # Using single quotes is invalid
    with patch("builtins.open", m):
        config = _load_json_config("config.json", DEFAULT_CONFIG)
        assert config == DEFAULT_CONFIG
