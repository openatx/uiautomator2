#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from unittest.mock import Mock, patch
import pytest

# 假设你的项目结构已经配置好，可以直接导入
from uiautomator2.ext.webview import SocketFinder, PortForwarder, WebViewExtension

# 全局 Mock 对象
mock_d = Mock()
mock_d.serial = "serial-123"
mock_d.shell.return_value.output = ""


def test_socket_finder_success():
    # 模拟 adb shell 返回了包含 webview socket 的字符串
    mock_output = """
    00000000: 00000002 00000000 00010000 0001 01 12345 @chrome_devtools_remote_111
    00000000: 00000002 00000000 00010000 0001 01 67890 @webview_devtools_remote_12345
    """
    mock_d.shell.return_value.output = mock_output
    
    # 使用 patch 跳过 sleep
    with patch('time.sleep', return_value=None):
        socket_name = SocketFinder.find(mock_d, timeout=1)
    
    assert socket_name == "webview_devtools_remote_12345"


def test_socket_finder_ignore_chrome():
    # 模拟只包含 chrome 的 socket，应该被忽略
    mock_output = "@chrome_devtools_remote_111"
    mock_d.shell.return_value.output = mock_output
    
    with patch('time.sleep', return_value=None):
        socket_name = SocketFinder.find(mock_d, timeout=0.1)
    
    assert socket_name is None


def test_socket_finder_timeout():
    # 模拟一直没有输出
    mock_d.shell.return_value.output = ""
    
    with patch('time.sleep', return_value=None):
        socket_name = SocketFinder.find(mock_d, timeout=0.1)
    
    assert socket_name is None


@patch('socket.socket')
@patch('uiautomator2.ext.webview.adb')
def test_port_forwarder_start(mock_adb, mock_socket_cls):
    # 1. 模拟获取空闲端口
    mock_socket = Mock()
    mock_socket_cls.return_value.__enter__.return_value = mock_socket
    mock_socket.getsockname.return_value = ('127.0.0.1', 11111)
    
    # 2. 模拟 adb device
    mock_device = Mock()
    mock_adb.device.return_value = mock_device
    
    # 初始化
    pf = PortForwarder("serial-123")
    assert pf.local_port == 11111
    
    # 执行 start
    port = pf.start("webview_socket_abc")
    
    # 验证
    assert port == 11111
    mock_adb.device.assert_called_with(serial="serial-123")
    mock_device.forward.assert_called_with("tcp:11111", "localabstract:webview_socket_abc")


@patch('uiautomator2.ext.webview.adb')
def test_port_forwarder_stop(mock_adb):
    # 模拟 PortForwarder 已经有一个端口
    # 这里我们 mock _get_free_port 来简化初始化
    with patch.object(PortForwarder, '_get_free_port', return_value=22222):
        pf = PortForwarder("serial-123")
        
        mock_device = Mock()
        mock_adb.device.return_value = mock_device
        
        # 执行 stop
        pf.stop()
        
        # 验证是否调用了 forward_remove
        mock_device.forward_remove.assert_called_with("tcp:22222")


@patch('uiautomator2.ext.webview.SocketFinder')
@patch('uiautomator2.ext.webview.PortForwarder')
@patch('uiautomator2.ext.webview.Chromium')
def test_webview_extension_attach_success(MockChromium, MockPortForwarder, MockSocketFinder):
    ext = WebViewExtension(mock_d)
    
    # 1. Mock 查找 Socket 成功
    MockSocketFinder.find.return_value = "socket_target"
    
    # 2. Mock 端口转发成功
    mock_pf_instance = MockPortForwarder.return_value
    mock_pf_instance.start.return_value = 55555
    
    # 3. Mock DrissionPage 连接
    mock_browser = Mock()
    MockChromium.return_value = mock_browser
    
    # 执行 attach
    result = ext.attach()
    
    # 验证流程
    MockSocketFinder.find.assert_called()
    mock_pf_instance.start.assert_called_with("socket_target")
    MockChromium.assert_called()
    assert result == mock_browser
    assert ext.browser == mock_browser


@patch('uiautomator2.ext.webview.SocketFinder')
def test_webview_extension_attach_socket_not_found(MockSocketFinder):
    ext = WebViewExtension(mock_d)
    # Mock 查找失败
    MockSocketFinder.find.return_value = None
    
    with pytest.raises(RuntimeError) as excinfo:
        ext.attach()
    
    assert "WebView Socket not detected" in str(excinfo.value)


@patch('uiautomator2.ext.webview.SocketFinder')
@patch('uiautomator2.ext.webview.PortForwarder')
@patch('uiautomator2.ext.webview.Chromium')
def test_webview_extension_attach_drission_failure(MockChromium, MockPortForwarder, MockSocketFinder):
    ext = WebViewExtension(mock_d)
    
    # 模拟前两步成功，但 Chromium 初始化失败
    MockSocketFinder.find.return_value = "socket_target"
    mock_pf_instance = MockPortForwarder.return_value
    
    MockChromium.side_effect = Exception("Connect Timeout")
    
    with pytest.raises(RuntimeError) as excinfo:
        ext.attach()
    
    assert "DrissionPage connection failed" in str(excinfo.value)
    # 关键：验证失败后是否清理了端口转发
    assert mock_pf_instance.stop.called


def test_webview_extension_detach():
    ext = WebViewExtension(mock_d)
    
    # 手动设置状态
    ext.browser = Mock()
    ext.forwarder = Mock()
    mock_forwarder_stop = ext.forwarder.stop
    
    ext.detach()
    
    assert ext.browser is None
    assert mock_forwarder_stop.called
    assert ext.forwarder is None


def test_webview_extension_current_page():
    ext = WebViewExtension(mock_d)
    
    # 成功情况
    mock_browser = Mock()
    expected_page = Mock()
    mock_browser.latest_tab = expected_page
    ext.browser = mock_browser
    
    assert ext.current_page == expected_page

    # 失败情况 (未 attach)
    ext.browser = None
    with pytest.raises(RuntimeError) as excinfo:
        _ = ext.current_page
        
    assert "Please call d.webview.attach() first" in str(excinfo.value)