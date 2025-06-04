from __future__ import absolute_import, print_function

import logging
import re
import time
from functools import cached_property
from typing import Any, Dict, List, Optional, Tuple, Union

import adbutils

from uiautomator2.core import BasicUiautomatorServer
from uiautomator2._proto import HTTP_TIMEOUT, SCROLL_STEPS, Direction
from uiautomator2.exceptions import *
from uiautomator2.settings import Settings
from uiautomator2.utils import image_convert, list2cmdline, deprecated
from uiautomator2.abstract import ShellResponse

logger = logging.getLogger(__name__)


class _BaseClient(BasicUiautomatorServer):
    """
    提供最基础的控制类，这个类暂时先不公开吧
    """

    def __init__(self, serial: Optional[Union[str, adbutils.AdbDevice]] = None):
        """
        Args:
            serial: device serialno
        """
        if isinstance(serial, adbutils.AdbDevice):
            self.__serial = serial.serial
            self._dev = serial
        else:
            self.__serial = serial
            self._dev = self._wait_for_device()
        self._debug = False
        BasicUiautomatorServer.__init__(self, self._dev)
    
    @property
    def _serial(self) -> str:
        return self.__serial
    
    def _wait_for_device(self, timeout=10) -> adbutils.AdbDevice:
        """
        wait for device came online, if device is remote, reconnect every 1s

        Returns:
            adbutils.AdbDevice
        
        Raises:
            ConnectError
        """
        for d in adbutils.adb.device_list():
            if d.serial == self._serial:
                return d

        _RE_remote_adb = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$")
        _is_remote = _RE_remote_adb.match(self._serial) is not None

        adb = adbutils.adb
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = "device reconnecting" if _is_remote else "wait-for-device"
            logger.debug("%s, time left(%.1fs)", title, deadline - time.time())
            if _is_remote:
                try:
                    adb.disconnect(self._serial)
                    adb.connect(self._serial, timeout=1)
                except (adbutils.AdbError, adbutils.AdbTimeout) as e:
                    logger.debug("adb reconnect error: %s", str(e))
                    time.sleep(1.0)
                    continue
            try:
                adb.wait_for(self._serial, timeout=1)
            except (adbutils.AdbError, adbutils.AdbTimeout):
                continue
            return adb.device(self._serial)
        raise ConnectError(f"device {self._serial} not online")

    @property
    def adb_device(self) -> adbutils.AdbDevice:
        return self._dev
    
    @cached_property
    def settings(self) -> Settings:
        return Settings(self)

    def sleep(self, seconds: float):
        """ same as time.sleep """
        time.sleep(seconds)

    def shell(self, cmdargs: Union[str, List[str]], timeout=60) -> ShellResponse:
        """
        Run shell command on device

        Args:
            cmdargs: str or list, example: "ls -l" or ["ls", "-l"]
            timeout: seconds of command run, works on when stream is False

        Returns:
            ShellResponse

        Raises:
            AdbShellError
        """
        try:
            if self.debug:
                print("shell:", list2cmdline(cmdargs))
            logger.debug("shell: %s", list2cmdline(cmdargs))
            ret = self._dev.shell2(cmdargs, timeout=timeout)
            return ShellResponse(ret.output, ret.returncode)
        except adbutils.AdbError as e:
            raise AdbShellError(e)

    @property
    def info(self) -> Dict[str, Any]:
        return self.jsonrpc.deviceInfo(http_timeout=10)
    
    @property
    def device_info(self) -> Dict[str, Any]:
        serial = self._dev.getprop("ro.serialno")
        sdk = self._dev.getprop("ro.build.version.sdk")
        version = self._dev.getprop("ro.build.version.release")
        brand = self._dev.getprop("ro.product.brand")
        model = self._dev.getprop("ro.product.model")
        arch = self._dev.getprop("ro.product.cpu.abi")
        return {
            "serial": serial,
            "sdk": int(sdk) if sdk.isdigit() else None,
            "brand": brand,
            "model": model,
            "arch": arch,
            "version": int(version) if version.isdigit() else None,
        }

    @property
    def wlan_ip(self) -> Optional[str]:
        try:
            return self._dev.wlan_ip()
        except adbutils.AdbError:
            return None

    @property
    def jsonrpc(self):
        class JSONRpcWrapper():
            def __init__(self, server: BasicUiautomatorServer):
                self.server = server
                self.method = None

            def __getattr__(self, method):
                self.method = method  # jsonrpc function name
                return self

            def __call__(self, *args, **kwargs):
                http_timeout = kwargs.pop('http_timeout', HTTP_TIMEOUT)
                params = args if args else kwargs
                return self.server.jsonrpc_call(self.method, params, http_timeout)

        return JSONRpcWrapper(self)

    def reset_uiautomator(self):
        """
        restart uiautomator service

        Orders:
            - stop uiautomator keeper
            - am force-stop com.github.uiautomator
            - start uiautomator keeper(am instrument -w ...)
            - wait until uiautomator service is ready
        """
        self.stop_uiautomator()
        self.start_uiautomator()

    def push(self, src, dst: str, mode=0o644):
        """
        Push file into device

        Args:
            src (path or fileobj): source file
            dst (str): destination can be folder or file path
            mode (int): file mode
        """
        self._dev.sync.push(src, dst, mode=mode)

    def pull(self, src: str, dst: str):
        """
        Pull file from device to local
        """
        try:
            self._dev.sync.pull(src, dst, exist_ok=True)
        except TypeError:
            self._dev.sync.pull(src, dst)
