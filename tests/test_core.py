# coding: utf-8
#

import hashlib
from unittest.mock import Mock, mock_open, patch

import pytest

from uiautomator2.core import BasicUiautomatorServer


@pytest.fixture
def mock_server():
    """Create a mock BasicUiautomatorServer instance with a mock device"""
    mock_dev = Mock()
    with patch.object(BasicUiautomatorServer, '__init__', return_value=None):
        server = BasicUiautomatorServer(None)
        server._dev = mock_dev
        yield server, mock_dev


class TestCheckDeviceFileHash:
    """Test the _check_device_file_hash method with toybox fallback"""
    
    def test_toybox_md5sum_success(self, mock_server):
        """Test when toybox md5sum command works correctly"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        local_md5 = hashlib.md5(test_content).hexdigest()
        
        # Mock the shell command to return toybox md5sum output
        # Format: "md5hash  filename"
        mock_dev.shell.return_value = f"{local_md5}  /data/local/tmp/u2.jar"
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is True (hash matches)
        assert result is True
        # Verify toybox md5sum was called
        mock_dev.shell.assert_called_once_with(["toybox", "md5sum", "/data/local/tmp/u2.jar"])
    
    def test_toybox_not_found_fallback_to_md5(self, mock_server):
        """Test fallback to md5 command when toybox is not found"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        local_md5 = hashlib.md5(test_content).hexdigest()
        
        # Mock the shell command to return different outputs
        # First call: toybox not found
        # Second call: md5 command output (format: "MD5 (filename) = md5hash")
        mock_dev.shell.side_effect = [
            "toybox: not found",
            f"MD5 (/data/local/tmp/u2.jar) = {local_md5}"
        ]
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is True (hash matches)
        assert result is True
        # Verify both commands were called
        assert mock_dev.shell.call_count == 2
        assert mock_dev.shell.call_args_list[0][0][0] == ["toybox", "md5sum", "/data/local/tmp/u2.jar"]
        assert mock_dev.shell.call_args_list[1][0][0] == ["md5", "/data/local/tmp/u2.jar"]
    
    def test_hash_mismatch(self, mock_server):
        """Test when the hash doesn't match"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        different_md5 = hashlib.md5(b"different content").hexdigest()
        
        # Mock the shell command to return a different hash
        mock_dev.shell.return_value = f"{different_md5}  /data/local/tmp/u2.jar"
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is False (hash doesn't match)
        assert result is False
    
    def test_md5_command_also_fails(self, mock_server):
        """Test when both toybox and md5 commands fail to find the file"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        
        # Mock the shell command to return errors for both commands
        mock_dev.shell.side_effect = [
            "toybox: not found",
            "md5: /data/local/tmp/u2.jar: No such file or directory"
        ]
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is False (file not found on device)
        assert result is False
