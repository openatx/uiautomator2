# coding: utf-8
# Test for selector behavior

from unittest.mock import MagicMock, Mock

import pytest

import uiautomator2 as u2
from uiautomator2._selector import Selector, UiObject
from uiautomator2.exceptions import UiObjectNotFoundError


def test_child_by_text_allow_scroll_search_exists_returns_false():
    """Test that child_by_text with allow_scroll_search=True returns False for .exists when element not found
    
    This tests the fix for the issue where child_by_text(allow_scroll_search=True).exists
    would raise UiObjectNotFoundError instead of returning False when the element is not found.
    """
    # Create mock session and jsonrpc
    mock_session = Mock()
    mock_jsonrpc = Mock()
    mock_session.jsonrpc = mock_jsonrpc
    
    # Setup: childByText raises UiObjectNotFoundError when element not found with allow_scroll_search=True
    mock_jsonrpc.childByText.side_effect = UiObjectNotFoundError(
        {'code': -32001, 'message': 'androidx.test.uiautomator.UiObjectNotFoundException'}
    )
    
    # Create a parent UiObject
    parent_selector = Selector(resourceId="test:id/parent")
    parent = UiObject(mock_session, parent_selector)
    
    # Call child_by_text with allow_scroll_search=True
    # This should NOT raise an exception
    child = parent.child_by_text("NonExistentText", allow_scroll_search=True)
    
    # Setup: exist() should return False for the sentinel selector
    mock_jsonrpc.exist.return_value = False
    
    # The .exists property should return False, not raise an exception
    assert not child.exists


def test_child_by_description_allow_scroll_search_exists_returns_false():
    """Test that child_by_description with allow_scroll_search=True returns False for .exists when element not found"""
    # Create mock session and jsonrpc
    mock_session = Mock()
    mock_jsonrpc = Mock()
    mock_session.jsonrpc = mock_jsonrpc
    
    # Setup: childByDescription raises UiObjectNotFoundError when element not found with allow_scroll_search=True
    mock_jsonrpc.childByDescription.side_effect = UiObjectNotFoundError(
        {'code': -32001, 'message': 'androidx.test.uiautomator.UiObjectNotFoundException'}
    )
    
    # Create a parent UiObject
    parent_selector = Selector(resourceId="test:id/parent")
    parent = UiObject(mock_session, parent_selector)
    
    # Call child_by_description with allow_scroll_search=True
    # This should NOT raise an exception
    child = parent.child_by_description("NonExistentDescription", allow_scroll_search=True)
    
    # Setup: exist() should return False for the sentinel selector
    mock_jsonrpc.exist.return_value = False
    
    # The .exists property should return False, not raise an exception
    assert not child.exists


def test_child_by_text_without_allow_scroll_search_raises_exception():
    """Test that child_by_text WITHOUT allow_scroll_search still raises exception (original behavior)"""
    # Create mock session and jsonrpc
    mock_session = Mock()
    mock_jsonrpc = Mock()
    mock_session.jsonrpc = mock_jsonrpc
    
    # Setup: childByText raises UiObjectNotFoundError
    mock_jsonrpc.childByText.side_effect = UiObjectNotFoundError(
        {'code': -32001, 'message': 'androidx.test.uiautomator.UiObjectNotFoundException'}
    )
    
    # Create a parent UiObject
    parent_selector = Selector(resourceId="test:id/parent")
    parent = UiObject(mock_session, parent_selector)
    
    # Call child_by_text WITHOUT allow_scroll_search=True
    # This SHOULD raise an exception (original behavior)
    with pytest.raises(UiObjectNotFoundError):
        parent.child_by_text("NonExistentText")


def test_child_by_text_allow_scroll_search_found_returns_true():
    """Test that child_by_text with allow_scroll_search=True returns True for .exists when element is found"""
    # Create mock session and jsonrpc
    mock_session = Mock()
    mock_jsonrpc = Mock()
    mock_session.jsonrpc = mock_jsonrpc
    
    # Setup: childByText returns a valid selector when element is found
    found_selector = Selector(text="FoundText")
    mock_jsonrpc.childByText.return_value = found_selector
    
    # Create a parent UiObject
    parent_selector = Selector(resourceId="test:id/parent")
    parent = UiObject(mock_session, parent_selector)
    
    # Call child_by_text with allow_scroll_search=True
    child = parent.child_by_text("FoundText", allow_scroll_search=True)
    
    # Setup: exist() should return True for the found element
    mock_jsonrpc.exist.return_value = True
    
    # The .exists property should return True
    assert child.exists
