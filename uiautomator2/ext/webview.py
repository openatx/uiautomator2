# Standard library imports
import socket
import subprocess
import time
import re

# Third-party imports
from DrissionPage import Chromium, ChromiumOptions


class SocketFinder:
    """负责查找 Android 内部的 WebView 调试接口"""
    
    @staticmethod
    def find(d, timeout=10):
        start_time = time.time()
        while time.time() - start_time < timeout:
            output = d.shell("cat /proc/net/unix | grep -a devtools_remote").output.strip()
            
            if output:
                lines = output.splitlines()
                # reverse search the newest
                for line in reversed(lines):
                    match = re.search(r'webview_devtools_remote_\d+', line)
                    if match:
                        socket_name = match.group(0)
                        return socket_name
            time.sleep(0.5)
        return None

class PortForwarder:
    """负责管理 ADB 端口转发"""
    
    def __init__(self, serial):
        self.serial = serial
        self.local_port = self._get_free_port()
        self.socket_name = None

    def _get_free_port(self):
        """获取本地空闲端口"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', 0))
            return s.getsockname()[1]

    def start(self, socket_name):
        self.socket_name = socket_name
        cmd = ["adb", "-s", self.serial, "forward", f"tcp:{self.local_port}", f"localabstract:{socket_name}"]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.local_port

    def stop(self):
        if self.local_port:
            cmd = ["adb", "-s", self.serial, "forward", "--remove", f"tcp:{self.local_port}"]
            subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class WebViewExtension:
    def __init__(self, d):
        self.d = d
        self.browser = None
        self.forwarder = None

    def attach(self, timeout=20):
        """
        连接当前设备的 WebView
        :param timeout: 等待 WebView Socket 出现的超时时间
        :return: DrissionPage.Chromium 对象 (浏览器实例)
        """
        # 1. find Socket
        socket_name = SocketFinder.find(self.d, timeout)
        
        if not socket_name:
            raise RuntimeError("未检测到 WebView Socket，请确认 App 已进入 H5 页面并开启了调试模式。")

        # 2. build forward
        if self.forwarder: 
            self.forwarder.stop() # 清理旧的
        
        self.forwarder = PortForwarder(self.d.serial)
        local_port = self.forwarder.start(socket_name)

        # 3. connect with DrissionPage
        try:
            co = ChromiumOptions()
            co.set_address(f'127.0.0.1:{local_port}')
            
            # 初始化浏览器对象
            # 注意：这里不需要 'browser_path'，因为是通过 address 接管
            self.browser = Chromium(addr_or_opts=co)
            
                
        except Exception as e:
            self.detach() # 失败则清理端口
            raise RuntimeError(f"DrissionPage 连接失败: {e}")

    def detach(self):
        """断开连接并清理端口转发"""
        if self.browser:
            self.browser = None
        
        if self.forwarder:
            self.forwarder.stop()
            self.forwarder = None

    @property
    def current_page(self):
        """
        快捷属性：获取当前激活的标签页 (Tab)
        适用于单页面应用或只关注当前屏幕的场景
        """ 
        if not self.browser:
            raise RuntimeError("请先调用 d.webview.attach()")
        return self.browser.latest_tab