import pytest
from unittest.mock import patch, mock_open
from utils.file_handler import save_json
import json
import os

# =================================================================
# file_handler.py のテスト
# =================================================================

@patch('utils.file_handler.util_str')
def test_save_json(mock_util_str):
    """Test that save_json calls its dependencies correctly and writes the correct data."""
    # Arrange
    domain = "example.com"
    directory = "data"
    expected_path = os.path.join(directory, f"{domain}.json")

    mock_util_str.get_domain.return_value = domain
    mock_util_str.util_handle_path.return_value = expected_path
    
    test_data = {"key": "value", "foo": "bar"}
    test_url = "http://example.com/some/path"
    
    # Act
    with patch('builtins.open', mock_open()) as mocked_file:
        save_json(test_data, test_url, directory=directory)
        
        # Assert
        mock_util_str.get_domain.assert_called_once_with(test_url)
        mock_util_str.util_handle_path.assert_called_once_with(expected_path)
        mocked_file.assert_called_once_with(expected_path, 'w', encoding='utf-8')
        
        # To check what was written to the file, we can inspect the mock's write calls
        handle = mocked_file()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        
        assert json.loads(written_data) == test_data
