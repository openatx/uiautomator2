#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for input method functionality"""

from unittest.mock import Mock, patch

import pytest

from uiautomator2._input import InputMethodMixIn
from uiautomator2.exceptions import AdbBroadcastError


class MockInputMethodMixIn(InputMethodMixIn):
    """Mock implementation for testing"""
    
    def __init__(self):
        self._adb_device = Mock()
        self._jsonrpc = Mock()
        self._broadcast_calls = []
        self._shell_calls = []
        self._current_ime = 'com.github.uiautomator/.AdbKeyboard'
    
    @property
    def adb_device(self):
        return self._adb_device
    
    @property 
    def jsonrpc(self):
        return self._jsonrpc
    
    def shell(self, args):
        """Mock shell method"""
        self._shell_calls.append(args)
        result = Mock()
        result.output = self._current_ime
        return result
    
    def _broadcast(self, action, extras=None):
        """Mock broadcast method"""
        from uiautomator2._input import BORADCAST_RESULT_OK, BroadcastResult
        self._broadcast_calls.append((action, extras or {}))
        return BroadcastResult(BORADCAST_RESULT_OK, "success")
    
    def __call__(self, **kwargs):
        """Mock selector call for fallback"""
        if not hasattr(self, '_mock_element'):
            self._mock_element = Mock()
            self._mock_element.set_text = Mock(return_value=True)
        return self._mock_element


def test_send_keys_hides_keyboard_when_using_custom_ime():
    """Test that send_keys hides keyboard after successful input with custom IME"""
    mock_input = MockInputMethodMixIn()
    
    # Test successful send_keys with custom IME
    result = mock_input.send_keys("hello world")
    
    # Should return True for successful operation
    assert result is True
    
    # Check broadcast calls - should have both input and hide calls
    broadcast_calls = mock_input._broadcast_calls
    assert len(broadcast_calls) >= 2
    
    # First call should be for input
    assert broadcast_calls[0][0] == "ADB_KEYBOARD_INPUT_TEXT"
    assert "text" in broadcast_calls[0][1]
    
    # Last call should be for hiding keyboard
    assert broadcast_calls[-1][0] == "ADB_KEYBOARD_HIDE"
    assert broadcast_calls[-1][1] == {}


def test_send_keys_fallback_does_not_hide_keyboard():
    """Test that send_keys fallback to set_text does not hide keyboard"""
    mock_input = MockInputMethodMixIn()
    
    # Mock the _must_broadcast to raise AdbBroadcastError for input text
    def failing_must_broadcast(action, extras=None):
        if action == "ADB_KEYBOARD_INPUT_TEXT":
            raise AdbBroadcastError("Simulated failure for input text")
        # Should not reach here (keyboard hide) in fallback mode
        raise AdbBroadcastError(f"Unexpected broadcast call: {action}")
    
    mock_input._must_broadcast = failing_must_broadcast
    
    # Test fallback behavior
    with patch('warnings.warn'):  # Suppress warning output
        result = mock_input.send_keys("hello world")
    
    # Should return the result from set_text (True in our mock)
    assert result is True
    
    # The element's set_text should have been called
    mock_element = mock_input(focused=True)
    assert mock_element.set_text.called
    mock_element.set_text.assert_called_with("hello world")


def test_hide_keyboard_method():
    """Test the hide_keyboard method directly"""
    mock_input = MockInputMethodMixIn()
    
    mock_input.hide_keyboard()
    
    # Should have made broadcast call for hiding
    broadcast_calls = mock_input._broadcast_calls
    assert len(broadcast_calls) >= 1
    assert broadcast_calls[-1][0] == "ADB_KEYBOARD_HIDE"
    assert broadcast_calls[-1][1] == {}