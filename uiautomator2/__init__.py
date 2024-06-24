#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function

import base64
import contextlib
import dataclasses
import io
import logging
import os
import re
import string
import time
import warnings
from functools import cached_property
from typing import Any, Dict, List, Optional, Union

import adbutils
from lxml import etree
from retry import retry
from PIL import Image

from uiautomator2.core import BasicUiautomatorServer

from uiautomator2 import xpath
from uiautomator2._proto import HTTP_TIMEOUT, SCROLL_STEPS, Direction
from uiautomator2._selector import Selector, UiObject
from uiautomator2._input import InputMethodMixIn
from uiautomator2.exceptions import AdbShellError, BaseException, ConnectError, DeviceError, HierarchyEmptyError, SessionBrokenError
from uiautomator2.settings import Settings
from uiautomator2.swipe import SwipeExt
from uiautomator2.utils import image_convert, list2cmdline, deprecated
from uiautomator2.watcher import WatchContext, Watcher
from uiautomator2.abstract import AbstractShell, AbstractUiautomatorServer, ShellResponse


WAIT_FOR_DEVICE_TIMEOUT = int(os.getenv("WAIT_FOR_DEVICE_TIMEOUT", 20))

logger = logging.getLogger(__name__)

def enable_pretty_logging(level=logging.DEBUG):
    if not logger.handlers:
        # Configure handler
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d pid:%(process)d] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level)


class _BaseClient(BasicUiautomatorServer, AbstractUiautomatorServer, AbstractShell):
    """
    提供最基础的控制类，这个类暂时先不公开吧
    """

    def __init__(self, serial: Union[str, adbutils.AdbDevice] = None):
        """
        Args:
            serial: device serialno
        """
        if isinstance(serial, adbutils.AdbDevice):
            self._serial = serial.serial
            self._dev = serial
        else:
            self._serial = serial
            self._dev = self._wait_for_device()
        self._debug = False
        BasicUiautomatorServer.__init__(self, self._dev)
    
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
            def __init__(self, server: "Device"):
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
        # https://developer.android.google.cn/training/monitoring-device-state/doze-standby
        # 让uiautomator进程不进入doze模式
        # help: dumpsys deviceidle help
        self.shell("dumpsys deviceidle whitelist +com.github.uiautomator; dumpsys deviceidle whitelist +com.github.uiautomator.test")
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
        self._dev.sync.pull(src, dst)

        # FIXME: check if windows still need f.close
        # with open(dst, 'wb') as f:
        #     shutil.copyfileobj(r.raw, f)
            # if _mswindows:  # FIXME: check hotfix windows file size zero bug
            #     f.close()


class _Device(_BaseClient):
    __orientation = (  # device orientation
        (0, "natural", "n", 0), (1, "left", "l", 90),
        (2, "upsidedown", "u", 180), (3, "right", "r", 270))

    def window_size(self):
        """ return (width, height) """
        w, h = self._dev.window_size()
        return w, h

    def screenshot(self, filename: Optional[str] = None, format="pillow", display_id: Optional[int] = None):
        """
        Take screenshot of device

        Returns:
            PIL.Image.Image, np.ndarray (OpenCV format) or None

        Args:
            filename (str): saved filename, if filename is set then return None
            format (str): used when filename is empty. one of ["pillow", "opencv", "raw"]
            display_id (int): use specific display if device has multiple screen

        Examples:
            screenshot("saved.jpg")
            screenshot().save("saved.png")
            cv2.imwrite('saved.jpg', screenshot(format='opencv'))
        """
        if display_id is None:
            base64_data = self.jsonrpc.takeScreenshot(1, 80)
            jpg_raw = base64.b64decode(base64_data)
            pil_img = Image.open(io.BytesIO(jpg_raw))
        else:
            pil_img = self._dev.screenshot(display_id=display_id)
        
        if filename:
            pil_img.save(filename)
            return
        return image_convert(pil_img, format)
        
    def dump_hierarchy(self, compressed=False, pretty=False, max_depth: int = None) -> str:
        """
        Dump window hierarchy

        Args:
            compressed (bool): return compressed xml
            pretty (bool): pretty print xml
            max_depth (int): max depth of hierarchy

        Returns:
            xml content
        """
        try:
            content = self._do_dump_hierarchy(compressed, max_depth)
        except HierarchyEmptyError:
            logger.warning("dump empty, return empty xml")
            content = '<?xml version=\'1.0\' encoding=\'UTF-8\' standalone=\'yes\' ?>\r\n<hierarchy rotation="0" />'
        
        if pretty:
            root = etree.fromstring(content.encode("utf-8"))
            content = etree.tostring(root, pretty_print=True, encoding=str)
        return content

    @retry(HierarchyEmptyError, tries=3, delay=1)
    def _do_dump_hierarchy(self, compressed=False, max_depth=None) -> str:
        if max_depth is None:
            max_depth = 50
        content = self.jsonrpc.dumpWindowHierarchy(compressed, max_depth)
        if content == "":
            raise HierarchyEmptyError("dump hierarchy is empty")
        
        # '<?xml version=\'1.0\' encoding=\'UTF-8\' standalone=\'yes\' ?>\r\n<hierarchy rotation="0" />'
        if '<hierarchy rotation="0" />' in content:
            logger.debug("dump empty, call clear_traversed_text and retry")
            # self.clear_traversed_text()
            raise HierarchyEmptyError("dump hierarchy is empty with no children")
        return content

    def implicitly_wait(self, seconds: float = None) -> float:
        """set default wait timeout
        Args:
            seconds(float): to wait element show up

        Returns:
            Current implicitly wait seconds

        Deprecated:
            recommend use: d.settings['wait_timeout'] = 10
        """
        if seconds:
            self.settings["wait_timeout"] = seconds
        return self.settings['wait_timeout']

    @property
    def pos_rel2abs(self):
        """
        returns a function which can convert percent size to pixel size
        """
        size = []

        def _convert(x, y):
            assert x >= 0
            assert y >= 0

            if (x < 1 or y < 1) and not size:
                size.extend(
                    self.window_size())  # size will be [width, height]

            if x < 1:
                x = int(size[0] * x)
            if y < 1:
                y = int(size[1] * y)
            return x, y

        return _convert

    @contextlib.contextmanager
    def _operation_delay(self, operation_name: str = None):
        before, after = self.settings['operation_delay']
        # 排除不要求延迟的方法
        if operation_name not in self.settings['operation_delay_methods']:
            before, after = 0, 0

        if before:
            logger.debug(f"operation [{operation_name}] pre-delay {before}s")
            time.sleep(before)
        yield
        if after:
            logger.debug(f"operation [{operation_name}] post-delay {after}s")
            time.sleep(after)

    @property
    def touch(self):
        """
        ACTION_DOWN: 0 ACTION_MOVE: 2
        touch.down(x, y)
        touch.move(x, y)
        touch.up(x, y)
        """
        ACTION_DOWN = 0
        ACTION_MOVE = 2
        ACTION_UP = 1

        obj: "Device" = self

        class _Touch(object):
            def down(self, x, y):
                x, y = obj.pos_rel2abs(x, y)
                obj.jsonrpc.injectInputEvent(ACTION_DOWN, x, y, 0)
                return self

            def move(self, x, y):
                x, y = obj.pos_rel2abs(x, y)
                obj.jsonrpc.injectInputEvent(ACTION_MOVE, x, y, 0)
                return self

            def up(self, x, y):
                """ ACTION_UP x, y """
                x, y = obj.pos_rel2abs(x, y)
                obj.jsonrpc.injectInputEvent(ACTION_UP, x, y, 0)
                return self

            def sleep(self, seconds: float):
                time.sleep(seconds)
                return self

        return _Touch()

    def click(self, x: Union[float, int], y: Union[float, int]):
        x, y = self.pos_rel2abs(x, y)
        with self._operation_delay("click"):
            self.jsonrpc.click(x, y)

    def double_click(self, x, y, duration=0.1):
        """
        double click position
        """
        x, y = self.pos_rel2abs(x, y)
        self.touch.down(x, y).up(x, y)
        time.sleep(duration)
        self.click(x, y)  # use click last is for htmlreport

    def long_click(self, x, y, duration: float = .5):
        '''long click at arbitrary coordinates.
        
        Args:
            duration (float): seconds of pressed
        '''
        x, y = self.pos_rel2abs(x, y)
        with self._operation_delay("click"):
            self.jsonrpc.click(x, y, int(duration*1000))

    def swipe(self, fx, fy, tx, ty, duration: Optional[float] = None, steps: Optional[int] = None):
        """
        Args:
            fx, fy: from position
            tx, ty: to position
            duration (float): duration
            steps: 1 steps is about 5ms, if set, duration will be ignore

        Documents:
            uiautomator use steps instead of duration
            As the document say: Each step execution is throttled to 5ms per step.

        Links:
            https://developer.android.com/reference/android/support/test/uiautomator/UiDevice.html#swipe%28int,%20int,%20int,%20int,%20int%29
        """
        if duration is not None and steps is not None:
            warnings.warn("duration and steps can not be set at the same time, use steps")
            duration = None
        if duration:
            steps = int(duration * 200)
        if not steps:
            steps = SCROLL_STEPS
        logger.debug("swipe from (%s, %s) to (%s, %s), steps: %d", fx, fy, tx, ty, steps)
        rel2abs = self.pos_rel2abs
        fx, fy = rel2abs(fx, fy)
        tx, ty = rel2abs(tx, ty)
        steps = max(2, steps)  # step=1 has no swipe effect
        with self._operation_delay("swipe"):
            return self.jsonrpc.swipe(fx, fy, tx, ty, steps)

    def swipe_points(self, points, duration: float = 0.5):
        """
        Args:
            points: is point array containg at least one point object. eg [[200, 300], [210, 320]]
            duration: duration to inject between two points

        Links:
            https://developer.android.com/reference/android/support/test/uiautomator/UiDevice.html#swipe(android.graphics.Point[], int)
        """
        ppoints = []
        rel2abs = self.pos_rel2abs
        for p in points:
            x, y = rel2abs(p[0], p[1])
            ppoints.append(x)
            ppoints.append(y)
        steps = int(duration * 200)
        return self.jsonrpc.swipePoints(ppoints, steps)

    def drag(self, sx, sy, ex, ey, duration=0.5):
        '''Swipe from one point to another point.'''
        rel2abs = self.pos_rel2abs
        sx, sy = rel2abs(sx, sy)
        ex, ey = rel2abs(ex, ey)
        with self._operation_delay("drag"):
            return self.jsonrpc.drag(sx, sy, ex, ey, int(duration * 200))

    def press(self, key: Union[int, str], meta=None):
        """
        press key via name or key code. Supported key name includes:
            home, back, left, right, up, down, center, menu, search, enter,
            delete(or del), recent(recent apps), volume_up, volume_down,
            volume_mute, camera, power.
        """
        with self._operation_delay("press"):
            if isinstance(key, int):
                return self.jsonrpc.pressKeyCode(
                    key, meta) if meta else self.jsonrpc.pressKeyCode(key)
            else:
                return self.jsonrpc.pressKey(key)
    
    def long_press(self, key: Union[int, str]):
        """
        long press key via name or key code

        Args:
            key: key name or key code
        
        Examples:
            long_press("home") same as "adb shell input keyevent --longpress KEYCODE_HOME"
        """
        with self._operation_delay("press"):
            if isinstance(key, int):
                self.shell("input keyevent --longpress %d" % key)
            else:
                key = key.upper()
                self.shell(f"input keyevent --longpress {key}")

    def screen_on(self):
        self.jsonrpc.wakeUp()

    def screen_off(self):
        self.jsonrpc.sleep()

    @property
    def orientation(self):
        '''
        orienting the devie to left/right or natural.
        left/l:       rotation=90 , displayRotation=1
        right/r:      rotation=270, displayRotation=3
        natural/n:    rotation=0  , displayRotation=0
        upsidedown/u: rotation=180, displayRotation=2
        '''
        return self.__orientation[self.info["displayRotation"]][1]

    def set_orientation(self, value):
        '''setter of orientation property.'''
        for values in self.__orientation:
            if value in values:
                # can not set upside-down until api level 18.
                self.jsonrpc.setOrientation(values[1])
                break
        else:
            raise ValueError("Invalid orientation.")

    def freeze_rotation(self, freezed: bool = True):
        self.jsonrpc.freezeRotation(freezed)

    @property
    def last_traversed_text(self):
        '''get last traversed text. used in webview for highlighted text.'''
        return self.jsonrpc.getLastTraversedText()

    def clear_traversed_text(self):
        '''clear the last traversed text.'''
        self.jsonrpc.clearLastTraversedText()

    def open_notification(self):
        return self.jsonrpc.openNotification()

    def open_quick_settings(self):
        return self.jsonrpc.openQuickSettings()

    def open_url(self, url: str):
        self.shell(
            ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url])

    def exists(self, **kwargs):
        return self(**kwargs).exists

    @property
    def clipboard(self) -> str:
        return super().clipboard
        # return self.jsonrpc.getClipboard() # FIXME(ssx): bug

    @clipboard.setter
    def clipboard(self, text: str):
        self.set_clipboard(text)

    def set_clipboard(self, text, label=None):
        '''
        Args:
            text: The actual text in the clip.
            label: User-visible label for the clip data.
        '''
        self.jsonrpc.setClipboard(label, text)

    def keyevent(self, v):
        """
        Args:
            v: eg home wakeup back
        """
        v = v.upper()
        self.shell("input keyevent " + v)

    @cached_property
    def serial(self) -> str:
        """
        If connected with USB, here should return self._serial
        When this situation happends

            d = u2.connect_usb("10.0.0.1:5555")
            d.serial # should be "10.0.0.1:5555"
            d.shell(['getprop', 'ro.serialno']).output.strip() # should uniq str like ffee123ca

        This logic should not change, because it used in tmq-service
        and if you break it, some people will not happy
        """
        if self._serial:
            return self._serial
        return self.shell(['getprop', 'ro.serialno']).output.strip()

    def show_float_window(self, show=True):
        """ 显示悬浮窗，提高uiautomator运行的稳定性 """
        arg = str(show).lower()
        self.shell([
            "am", "start", "-n", "com.github.uiautomator/.ToastActivity", "-e",
            "showFloatWindow", arg
        ])

    @property
    def toast(self):
        obj = self

        class Toast(object):
            def get_message(self,
                            wait_timeout=10,
                            cache_timeout=10,
                            default=None):
                """
                Args:
                    wait_timeout: seconds of max wait time if toast now show right now
                    cache_timeout: return immediately if toast showed in recent $cache_timeout
                    default: default messsage to return when no toast show up

                Returns:
                    None or toast message
                """
                deadline = time.time() + wait_timeout
                while 1:
                    message = obj.jsonrpc.getLastToast(cache_timeout * 1000)
                    if message:
                        return message
                    if time.time() > deadline:
                        return default
                    time.sleep(.5)

            def reset(self):
                return obj.jsonrpc.clearLastToast()

            def show(self, text, duration=1.0):
                return obj.jsonrpc.makeToast(text, duration * 1000)

        return Toast()
    
    def __call__(self, **kwargs):
        return UiObject(self, Selector(**kwargs))


class _AppMixIn(AbstractShell):
    def session(self, package_name: str, attach: bool = False) -> "Session":
        """
        launch app and keep watching the app's state

        Args:
            package_name: package name
            attach: attach to existing session or not

        Returns:
            Session
        """
        self.app_start(package_name, stop=not attach)
        return Session(self.adb_device, package_name)

    def _compat_shell_ps(self) -> str:
        """
        Compatible with some devices that does not support `ps` command
        """
        output = self.shell("ps -A").output
        if len(output.strip().splitlines()) <= 1:
            output = self.shell("ps").output
        return output.strip().replace("\r\n", "\n")
        
    def _pidof_app(self, package_name) -> Optional[int]:
        """
        Return pid of package name
        """
        output = self._compat_shell_ps()
        lines = output.splitlines()
        for line in lines:
            # line example: u0_a1    1318  123   1010000 27580 SyS_epoll_ 0000000000 S com.github.uiautomator
            fields = line.strip().split()
            if len(fields) < 9:
                continue
            if fields[-1] == package_name:
                return int(fields[1])

    def app_current(self):
        """
        Returns:
            dict(package, activity, pid?)

        Raises:
            DeviceError

        For developer:
            Function reset_uiautomator need this function, so can't use jsonrpc here.
        """
        info = self.adb_device.app_current()
        if info:
            return dataclasses.asdict(info)
        raise DeviceError("Couldn't get focused app")

    def app_install(self, data: str):
        """
        Install app

        Args:
            data: can be file path or url or file object
        """
        self.adb_device.install(data)

    def wait_activity(self, activity, timeout=10) -> bool:
        """ wait activity
        Args:
            activity (str): name of activity
            timeout (float): max wait time

        Returns:
            bool of activity
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            current_activity = self.app_current().get('activity')
            if activity == current_activity:
                return True
            time.sleep(.5)
        return False

    def app_start(self, package_name: str, activity: Optional[str] = None, wait: bool = False, stop: bool = False, use_monkey: bool = False):
        """ Launch application
        Args:
            package_name (str): package name
            activity (str): app activity
            stop (bool): Stop app before starting the activity. (require activity)
            use_monkey (bool): use monkey command to start app when activity is not given
            wait (bool): wait until app started. default False
        """
        if stop:
            self.app_stop(package_name)

        if use_monkey or not activity:
            self.shell([
                'monkey', '-p', package_name, '-c',
                'android.intent.category.LAUNCHER', '1'
            ])
            if wait:
                self.app_wait(package_name)
            return

        # if not activity:
        #     info = self.app_info(package_name)
        #     activity = info['mainActivity']
        #     if activity.find(".") == -1:
        #         activity = "." + activity

        # -D: enable debugging
        # -W: wait for launch to complete
        # -S: force stop the target app before starting the activity
        # --user <USER_ID> | current: Specify which user to run as; if not
        #    specified then run as the current user.
        # -e <EXTRA_KEY> <EXTRA_STRING_VALUE>
        # --ei <EXTRA_KEY> <EXTRA_INT_VALUE>
        # --ez <EXTRA_KEY> <EXTRA_BOOLEAN_VALUE>
        args = [
            'am', 'start', '-a', 'android.intent.action.MAIN', '-c',
            'android.intent.category.LAUNCHER',
            '-n', f'{package_name}/{activity}'
        ]
        self.shell(args)

        if wait:
            self.app_wait(package_name)

    def app_wait(self,
                 package_name: str,
                 timeout: float = 20.0,
                 front=False) -> int:
        """ Wait until app launched
        Args:
            package_name (str): package name
            timeout (float): maxium wait time
            front (bool): wait until app is current app

        Returns:
            pid (int) 0 if launch failed
        """
        pid = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if front:
                if self.app_current()['package'] == package_name:
                    pid = self._pidof_app(package_name)
            else:
                if package_name in self.app_list_running():
                    pid = self._pidof_app(package_name)
            if pid:
                return pid
            time.sleep(1)

        return pid or 0

    def app_list(self, filter: str = None) -> List[str]:
        """
        List installed app package names

        Args:
            filter: [-f] [-d] [-e] [-s] [-3] [-i] [-u] [--user USER_ID] [FILTER]
        
        Returns:
            list of apps by filter
        """
        output, _ = self.shell(['pm', 'list', 'packages', filter])
        packages = re.findall(r'package:([^\s]+)', output)
        return list(packages)

    def app_list_running(self) -> List[str]:
        """
        Returns:
            list of running apps
        """
        output, _ = self.shell('pm list packages')
        packages = re.findall(r'package:([^\s]+)', output)
        ps_output = self._compat_shell_ps()
        process_names = re.findall(r'(\S+)$', ps_output, re.M)
        return list(set(packages).intersection(process_names))

    def app_stop(self, package_name: str):
        """ Stop one application """
        self.adb_device.app_stop(package_name)

    def app_stop_all(self, excludes=[]):
        """ Stop all third party applications
        Args:
            excludes (list): apps that do now want to kill

        Returns:
            a list of killed apps
        """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        kill_pkgs = set(self.app_list_running()).difference(our_apps +
                                                            excludes)
        for pkg_name in kill_pkgs:
            self.app_stop(pkg_name)
        return list(kill_pkgs)

    def app_clear(self, package_name: str):
        """ Stop and clear app data: pm clear """
        self.adb_device.app_clear(package_name)

    def app_uninstall(self, package_name: str) -> bool:
        """ Uninstall an app 

        Returns:
            bool: success
        """
        ret = self.shell(["pm", "uninstall", package_name])
        return ret.exit_code == 0

    def app_uninstall_all(self, excludes=[], verbose=False):
        """ Uninstall all apps """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        output, _ = self.shell(['pm', 'list', 'packages', '-3'])
        pkgs = re.findall(r'package:([^\s]+)', output)
        pkgs = set(pkgs).difference(our_apps + excludes)
        pkgs = list(pkgs)
        for pkg_name in pkgs:
            if verbose:
                print("uninstalling", pkg_name, " ", end="", flush=True)
            ok = self.app_uninstall(pkg_name)
            if verbose:
                print("OK" if ok else "FAIL")

        return pkgs

    def app_info(self, package_name: str) -> Dict[str, Any]:
        """
        Get app info

        Args:
            package_name (str): package name

        Return example:
            {
                "versionName": "1.1.7",
                "versionCode": 1001007
            }

        Raises:
            UiaError
        """
        info = self.adb_device.app_info(package_name)
        if not info:
            raise BaseException("App not installed")
        return {
            "versionName": info.version_name,
            "versionCode": info.version_code,
        }

    def app_auto_grant_permissions(self, package_name: str):
        """ auto grant permissions

        Args:
            package_name (str): package name
        
        Help of "adb shell pm":
            grant [--user USER_ID] PACKAGE PERMISSION
            revoke [--user USER_ID] PACKAGE PERMISSION
                These commands either grant or revoke permissions to apps.  The permissions
                must be declared as used in the app's manifest, be runtime permissions
                (protection level dangerous), and the app targeting SDK greater than Lollipop MR1 (API level 22).
        
        Help of "Android official pm" see <https://developer.android.com/tools/adb#pm>
            Grant a permission to an app. On devices running Android 6.0 (API level 23) and higher,
              the permission can be any permission declared in the app manifest.
            On devices running Android 5.1 (API level 22) and lower,
              must be an optional permission defined by the app.
        """
        sdk_version_output = self.shell(['getprop', 'ro.build.version.sdk']).output.strip()
        sdk_version = int(sdk_version_output) if sdk_version_output.isdigit() else None
        if sdk_version is None:
            logger.warning("can't get sdk version")
            return
        if sdk_version < 23:
            # TODO: support android 5.1 (API 22) and lower
            logger.warning("auto grant permissions only support android 6.0+ (API 23+)")
            return
        
        dumpsys_package_output = self.shell(['dumpsys', 'package',  package_name]).output
        target_sdk_match = re.search(r'targetSdk=(\d+)', dumpsys_package_output)
        if not target_sdk_match:
            logger.warning("can't get targetSdk from dumpsys package")
            return
        target_sdk = int(target_sdk_match.group(1))
        if target_sdk < 22:
            logger.warning("auto grant permissions only support app targetSdk >= 22")
            return
            
        permissions = re.findall(r'(android\.\w*\.?permission\.\w+): granted=false', dumpsys_package_output)
        for permission in permissions:
            self.shell(['pm', 'grant', package_name, permission])
            logger.info(f'auto grant permission {permission}')


class _DeprecatedMixIn:
    @property
    def wait_timeout(self):  # wait element timeout
        return self.settings['wait_timeout']

    @wait_timeout.setter
    def wait_timeout(self, v: Union[int, float]):
        self.settings['wait_timeout'] = v

    @property
    def click_post_delay(self):
        """ Deprecated or not deprecated, this is a question """
        return self.settings['post_delay']

    @click_post_delay.setter
    def click_post_delay(self, v: Union[int, float]):
        self.settings['post_delay'] = v

    @deprecated(reason="use d.toast.show(text, duration) instead")
    def make_toast(self, text, duration=1.0):
        """ Show toast
        Args:
            text (str): text to show
            duration (float): seconds of display
        """
        return self.jsonrpc.makeToast(text, duration * 1000)

    def unlock(self):
        """ unlock screen with swipe from left-bottom to right-top """
        if not self.info['screenOn']:
            self.shell("input keyevent WAKEUP")
            self.swipe(0.1, 0.9, 0.9, 0.1)



class _PluginMixIn:
    def watch_context(self, autostart: bool = True, builtin: bool = False) -> WatchContext:
        wc = WatchContext(self, builtin=builtin)
        if autostart:
            wc.start()
        return wc

    @cached_property
    def watcher(self) -> Watcher:
        return Watcher(self)

    @cached_property
    def xpath(self) -> xpath.XPathEntry:
        return xpath.XPathEntry(self)

    @cached_property
    def image(self):
        from uiautomator2 import image as _image
        return _image.ImageX(self)

    @cached_property
    def screenrecord(self):
        from uiautomator2 import screenrecord as _sr
        return _sr.Screenrecord(self)

    @cached_property
    def swipe_ext(self) -> SwipeExt:
        return SwipeExt(self)


class Device(_Device, _AppMixIn, _PluginMixIn, InputMethodMixIn, _DeprecatedMixIn):
    """ Device object """
    pass


class Session(Device):
    """Session keeps watch the app status
    each jsonrpc call will check if the package is still running
    """
    def __init__(self, dev: adbutils.AdbDevice, package_name: str):
        super().__init__(dev)
        self._package_name = package_name
        self._pid = self.app_wait(self._package_name)
    
    def running(self) -> bool:
        return self._pid == self._pidof_app(self._package_name)

    @property
    def pid(self) -> int:
        return self._pid
        
    def jsonrpc_call(self, method: str, params: Any = None, timeout: float = 10) -> Any:
        if not self.running():
            raise SessionBrokenError(f"app:{self._package_name} pid:{self._pid} is quit")
        return super().jsonrpc_call(method, params, timeout)
    
    def restart(self):
        """ restart app """
        self.app_start(self._package_name, wait=True, stop=True)
        self._pid = self._pidof_app(self._package_name)
    
    def close(self):
        """ close app """
        self.app_stop(self._package_name)
        self._pid = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def connect(serial: Union[str, adbutils.AdbDevice] = None) -> Device:
    """
    Args:
        serial (str): Android device serialno

    Returns:
        Device

    Raises:
        ConnectError

    Example:
        connect("10.0.0.1:5555")
        connect("cff1123ea")  # adb device serial number
    """
    if not serial:
        serial = os.getenv("ANDROID_SERIAL")
    return connect_usb(serial)


def connect_usb(serial: Optional[str] = None) -> Device:
    """
    Args:
        serial (str): android device serial

    Returns:
        Device

    Raises:
        ConnectError
    """
    if not serial:
        serial = adbutils.adb.device()
    return Device(serial)