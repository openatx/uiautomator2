# Standard library imports
import socket
import time
import re
import traceback

# Third-party imports
from adbutils import adb
from DrissionPage import Chromium, ChromiumOptions

class SocketFinder:
    """负责查找 Android 内部的 WebView 调试接口"""
    
    @staticmethod
    def find(d, timeout=10, retry_interval=0.5):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                output = d.shell("cat /proc/net/unix | grep -a devtools_remote").output.strip()
                
                if output:
                    lines = output.splitlines()
                    # reverse search the newest
                    for line in reversed(lines):
                        match = re.search(r'webview_devtools_remote_\d+', line)
                        if match:
                            socket_name = match.group(0)
                            return socket_name
            except Exception as e:
                print(f"[SocketFinder] Shell command failed: {e}")
            time.sleep(retry_interval)
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
        adb.device(serial=self.serial).forward(f"tcp:{self.local_port}", f"localabstract:{socket_name}")
        return self.local_port

    def stop(self):
        if self.local_port:
            try:
                adb.device(serial=self.serial).forward_remove(f"tcp:{self.local_port}")
            except Exception:
                traceback.print_exc()

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
            raise RuntimeError("WebView Socket not detected. Please ensure App is on H5 page and debugging is enabled.")

        # 2. build forward
        if self.forwarder: 
            self.forwarder.stop()
        
        self.forwarder = PortForwarder(self.d.serial)
        local_port = self.forwarder.start(socket_name)

        # 3. connect with DrissionPage
        try:
            co = ChromiumOptions()
            co.set_address(f'127.0.0.1:{local_port}')
            self.browser = Chromium(addr_or_opts=co)
            return self.browser
        except Exception as e:
            self.detach() # 失败则清理端口
            raise RuntimeError(f"DrissionPage connection failed: {e}")

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
            raise RuntimeError("Please call d.webview.attach() first")
        return self.browser.latest_tab