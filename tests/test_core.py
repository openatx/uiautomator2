# coding: utf-8
#

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from uiautomator2.core import BasicUiautomatorServer


def test_check_device_file_hash_with_toybox():
    """Test _check_device_file_hash when toybox md5sum is available"""
    # Create a temporary file to test with
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"test content")
        tmp_path = tmp_file.name
    
    try:
        # Calculate MD5 of the test file
        md5 = hashlib.md5()
        md5.update(b"test content")
        expected_md5 = md5.hexdigest()
        
        # Mock the device
        mock_dev = Mock()
        # Simulate toybox md5sum output (format: "hash  filename")
        mock_dev.shell.return_value = f"{expected_md5}  /data/local/tmp/test.jar"
        
        # Create server instance with mocked device and patched start_uiautomator
        with patch.object(BasicUiautomatorServer, 'start_uiautomator'):
            server = BasicUiautomatorServer.__new__(BasicUiautomatorServer)
            server._dev = mock_dev
            
            # Test the method
            result = server._check_device_file_hash(tmp_path, "/data/local/tmp/test.jar")
            
            # Verify it called shell with toybox md5sum
            mock_dev.shell.assert_called_once_with(["toybox", "md5sum", "/data/local/tmp/test.jar"])
            
            # Verify it returns True when hash matches
            assert result is True
    finally:
        Path(tmp_path).unlink()


def test_check_device_file_hash_fallback_to_md5():
    """Test _check_device_file_hash falls back to md5 when toybox is not found"""
    # Create a temporary file to test with
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"test content")
        tmp_path = tmp_file.name
    
    try:
        # Calculate MD5 of the test file
        md5 = hashlib.md5()
        md5.update(b"test content")
        expected_md5 = md5.hexdigest()
        
        # Mock the device
        mock_dev = Mock()
        # First call returns "not found" error from toybox
        # Second call returns md5 output (format for Android md5: "MD5 (filename) = hash")
        mock_dev.shell.side_effect = [
            "/system/bin/sh: toybox: not found",  # First call - toybox not found
            f"MD5 (/data/local/tmp/test.jar) = {expected_md5}"  # Second call - md5 command
        ]
        
        # Create server instance with mocked device and patched start_uiautomator
        with patch.object(BasicUiautomatorServer, 'start_uiautomator'):
            server = BasicUiautomatorServer.__new__(BasicUiautomatorServer)
            server._dev = mock_dev
            
            # Test the method
            result = server._check_device_file_hash(tmp_path, "/data/local/tmp/test.jar")
            
            # Verify it called shell twice - first toybox, then md5
            assert mock_dev.shell.call_count == 2
            assert mock_dev.shell.call_args_list[0][0][0] == ["toybox", "md5sum", "/data/local/tmp/test.jar"]
            assert mock_dev.shell.call_args_list[1][0][0] == ["md5", "/data/local/tmp/test.jar"]
            
            # Verify it returns True when hash matches
            assert result is True
    finally:
        Path(tmp_path).unlink()


def test_check_device_file_hash_mismatch():
    """Test _check_device_file_hash returns False when hash doesn't match"""
    # Create a temporary file to test with
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"test content")
        tmp_path = tmp_file.name
    
    try:
        # Mock the device with a different hash
        mock_dev = Mock()
        mock_dev.shell.return_value = "differenthash123456  /data/local/tmp/test.jar"
        
        # Create server instance with mocked device and patched start_uiautomator
        with patch.object(BasicUiautomatorServer, 'start_uiautomator'):
            server = BasicUiautomatorServer.__new__(BasicUiautomatorServer)
            server._dev = mock_dev
            
            # Test the method
            result = server._check_device_file_hash(tmp_path, "/data/local/tmp/test.jar")
            
            # Verify it returns False when hash doesn't match
            assert result is False
    finally:
        Path(tmp_path).unlink()


def test_check_device_file_hash_fallback_mismatch():
    """Test _check_device_file_hash with fallback returns False when hash doesn't match"""
    # Create a temporary file to test with
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"test content")
        tmp_path = tmp_file.name
    
    try:
        # Mock the device
        mock_dev = Mock()
        # First call returns "not found" error from toybox
        # Second call returns md5 output with different hash
        mock_dev.shell.side_effect = [
            "/system/bin/sh: toybox: not found",  # First call - toybox not found
            "MD5 (/data/local/tmp/test.jar) = differenthash123456"  # Second call - different hash
        ]
        
        # Create server instance with mocked device and patched start_uiautomator
        with patch.object(BasicUiautomatorServer, 'start_uiautomator'):
            server = BasicUiautomatorServer.__new__(BasicUiautomatorServer)
            server._dev = mock_dev
            
            # Test the method
            result = server._check_device_file_hash(tmp_path, "/data/local/tmp/test.jar")
            
            # Verify it returns False when hash doesn't match
            assert result is False
    finally:
        Path(tmp_path).unlink()
