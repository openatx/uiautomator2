#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
::Timeout

atx-agent:ReverseProxy use http.DefaultTransport. Default Timeout: 30s

|-- Dial --|-- TLS handshake --|-- Request --|-- Resp.headers --|-- Respose.body --|
|------------------------------ http.Client.Timeout -------------------------------|

Refs:
    - https://golang.org/pkg/net/http/#RoundTripper
    - http://colobu.com/2016/07/01/the-complete-guide-to-golang-net-http-timeouts
"""

from __future__ import absolute_import, print_function

import base64
import contextlib
import functools
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import warnings
import xml.dom.minidom
from collections import namedtuple, defaultdict
from datetime import datetime
from typing import List, Optional, Tuple, Union

# import progress.bar
import adbutils
import packaging
import requests
import six
import six.moves.urllib.parse as urlparse
from cached_property import cached_property
from deprecated import deprecated
from logzero import setup_logger
from PIL import Image
from retry import retry
from urllib3.util.retry import Retry

from . import xpath
from ._selector import Selector, UiObject
from .exceptions import (BaseError, ConnectError, GatewayError, JSONRPCError,
                         NullObjectExceptionError, NullPointerExceptionError,
                         RetryError, ServerError, SessionBrokenError,
                         StaleObjectExceptionError,
                         UiAutomationNotConnectedError, UiObjectNotFoundError)
from .init import Initer
# from .session import Session  # noqa: F401
from .settings import Settings
from .swipe import SwipeExt
from .utils import list2cmdline
from .version import __atx_agent_version__, __apk_version__
from .watcher import Watcher, WatchContext
from ._proto import SCROLL_STEPS, Direction, HTTP_TIMEOUT

if six.PY2:
    FileNotFoundError = OSError

DEBUG = False
WAIT_FOR_DEVICE_TIMEOUT = int(os.getenv("WAIT_FOR_DEVICE_TIMEOUT", 20))

# logger = logging.getLogger("uiautomator2")

logger = setup_logger("uiautomator2", level=logging.DEBUG)
_mswindows = (os.name == "nt")


class TimeoutRequestsSession(requests.Session):
    def __init__(self):
        super(TimeoutRequestsSession, self).__init__()
        # refs: https://stackoverflow.com/questions/33895739/python-requests-cant-load-any-url-remote-end-closed-connection-without-respo
        # refs: https://stackoverflow.com/questions/15431044/can-i-set-max-retries-for-requests-request

        # Is retry necessary, maybe not, so I closed it at 2020/05/29
        # retries = Retry(total=3, connect=3, backoff_factor=0.5)
        # adapter = requests.adapters.HTTPAdapter(max_retries=retries)
        # self.mount("http://", adapter)
        # self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        # Init timeout and set connect-timeout to 3s
        if 'timeout' not in kwargs:
            kwargs['timeout'] = (3, HTTP_TIMEOUT)
        if isinstance(kwargs['timeout'], (int, float)):
            kwargs['timeout'] = (3, kwargs['timeout'])

        verbose = hasattr(self, 'debug') and self.debug
        if verbose:
            data = kwargs.get('data') or '""'
            if isinstance(data, dict):
                data = json.dumps(data)
            time_start = time.time()
            print(datetime.now().strftime("%H:%M:%S.%f")[:-3],
                  "$ curl -X {method} -d '{data}' '{url}'".format(
                      method=method, url=url, data=data))  # yaml: disable
        try:
            resp = super(TimeoutRequestsSession,
                         self).request(method, url, **kwargs)
        except requests.ConnectionError as e:
            # High possibly atx-agent is down
            raise
        else:
            if verbose:
                print(
                    datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "Response (%d ms) >>>\n" %
                    ((time.time() - time_start) * 1000) + resp.text.rstrip() +
                    "\n<<< END")

            from types import MethodType

            def raise_for_status(_self):
                if _self.status_code != 200:
                    raise requests.HTTPError(_self.status_code, _self.text)

            resp.raise_for_status = MethodType(raise_for_status, resp)
            return resp


ShellResponse = namedtuple("ShellResponse", ("output", "exit_code"))


def _is_production():
    # support change to production use: os.environ['TMQ'] = 'true'
    return (os.environ.get("TMQ") == "true")


class _Service(object):
    def __init__(self, name, u2obj: "Device"):
        self.name = name
        # FIXME(ssx): support other service: minicap, minitouch
        assert name == 'uiautomator'
        self.u2obj = u2obj
        self.service_url = self.u2obj.path2url("/services/" + name)

    def _raise_for_status(self, res: requests.Response):
        if res.status_code != 200:
            if res.headers['content-type'].startswith("application/json"):
                raise RuntimeError(res.json()["description"])
            warnings.warn(res.text)
            res.raise_for_status()

    def start(self):
        """
        Manually run with the following command:
            adb shell am instrument -w -r -e debug false -e class com.github.uiautomator.stub.Stub \
                com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner
        """
        # kill uiautomator
        res = self.u2obj.http.post(self.service_url)
        self._raise_for_status(res)

    def stop(self):
        """
        1. stop command which launched with uiautomator 1.0
            Eg: adb shell uiautomator runtest androidUiAutomator.jar
        """
        res = self.u2obj.http.delete(self.service_url)
        self._raise_for_status(res)

    def running(self) -> bool:
        res = self.u2obj.http.get(self.service_url)
        self._raise_for_status(res)
        return res.json().get("running")


class _AgentRequestSession(TimeoutRequestsSession):
    def __init__(self, clnt: "_BaseClient"):
        super().__init__()
        self.__client = clnt

    def request(self, method, url, **kwargs):
        """
        Raises:
            RuntimeError
        """
        retry = kwargs.pop("retry", True)
        try:
            # may raise adbutils.AdbError when device offline
            url = self.__client.path2url(url)
            return super().request(method, url, **kwargs)
        except (requests.ConnectionError, requests.ReadTimeout,
                adbutils.AdbError) as e:
            if not retry:
                raise
            # if atx-agent is already running, just raise error
            if isinstance(e, requests.RequestException) and \
                    self.__client._is_agent_alive():
                raise


        if not self.__client._serial:
            raise OSError(
                "http-request to atx-agent error, can only recover from USB")

        logger.warning("atx-agent has something wrong, auto recovering")
        # ReadTimeout: sometime means atx-agent is running but not responsing
        # one reason is futex_wait_queue: https://stackoverflow.com/questions/9801256/app-hangs-on-futex-wait-queue-me-every-a-couple-of-minutes

        # fix atx-agent and request again
        self.__client._prepare_atx_agent()
        url = self.__client.path2url(url)
        return super().request(method, url, **kwargs)


class _BaseClient(object):
    """
    提供最基础的控制类，这个类暂时先不公开吧
    """

    def __init__(self, serial_or_url: Optional[str] = None):
        """
        Args:
            serial_or_url: device serialno or atx-agent base url

        Example:
            serial_or_url support param like
            - 08a3d291
            - http://10.0.0.1:7912
        """
        if not serial_or_url:
            # should only one usb device connected
            serial_or_url = adbutils.adb.device().serial

        if re.match(r"^https?://", serial_or_url):
            self._serial = None
            self._atx_agent_url = serial_or_url
            return

        # USB 连接
        self._serial = serial_or_url
        self._atx_agent_url = None

        # fallback to wifi if USB disconnected
        wlan_ip = self.wlan_ip
        if wlan_ip:
            self._atx_agent_url = f"http://{wlan_ip}:7912"

    def _get_atx_agent_url(self) -> str:
        """ get url for python client to connect """
        if not self._serial:
            return self._atx_agent_url

        try:
            lport = self._adb_device.forward_port(
                7912)  # this method is so fast, only take 0.2ms
            return f"http://127.0.0.1:{lport}"
        except adbutils.AdbError as e:
            if not _is_production() and self._atx_agent_url:
                # when device offline, use atx-agent-url
                logger.info(
                    "USB disconnected, fallback to WiFi, ATX_AGENT_URL=%s",
                    self._atx_agent_url)
                return self._atx_agent_url
            raise

    def _get_atx_agent_path(self) -> str:
        return "/data/local/tmp/atx-agent"

    def path2url(self, path: str) -> str:
        """ relative url path to full url path """
        if re.match(r"^(ws|http)s?://", path):
            return path
        return urlparse.urljoin(self._get_atx_agent_url(), path)

    @property
    def _adb_device(self):
        """ only avaliable when connected with usb """
        assert self._serial, "serial should not empty"
        return adbutils.adb.device(serial=self._serial)

    def _prepare_atx_agent(self):
        """
        check running -> push binary -> launch
        """
        assert self._serial, "Device serialno is required"
        _d = self._wait_for_device()
        if not _d:
            raise RuntimeError("USB device %s is offline" % self._serial)
        logger.debug("device %s is online", self._serial)
        version_url = self.path2url("/version")
        try:
            version = requests.get(version_url, timeout=3).text
            if version != __atx_agent_version__:
                raise EnvironmentError("atx-agent need upgrade")
        except (requests.RequestException, EnvironmentError):
            self._setup_atx_agent()

        # return self._get_atx_agent_url()

    def _setup_atx_agent(self):
        # check running
        self._kill_process_by_name("atx-agent", use_adb=True)

        from uiautomator2 import init
        _initer = init.Initer(self._adb_device)
        if not _initer.check_install():
            _initer.install()
        else:
            _initer.start_atx_agent()
        _initer.check_atx_agent_version()

    def _wait_for_device(self, timeout=None) -> adbutils.AdbDevice:
        """
        wait for device came online, if device is remote, reconnect every 1s

        Returns:
            adbutils.AdbDevice or None
        """
        if not timeout:
            timeout = WAIT_FOR_DEVICE_TIMEOUT if _is_production() else 3.0

        for d in adbutils.adb.device_list():
            if d.serial == self._serial:
                return d

        _RE_remote_adb = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$")
        _is_remote = _RE_remote_adb.match(self._serial) is not None

        adb = adbutils.adb
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = "device reconnecting" if _is_remote else "wait-for-device"
            logger.info("%s, time left(%.1fs)", title, deadline - time.time())
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
            except adbutils.AdbTimeout:
                continue
            
            return adb.device(self._serial)
        return None

    def _adb_shell(self, cmdargs: Union[list, Tuple[str]], timeout=None):
        """ run command through adb command """
        return self._adb_device.shell(cmdargs, timeout=timeout)

    def _setup_uiautomator(self):
        self.shell(["pm", "uninstall", "com.github.uiautomator"])
        self.shell(["pm", "uninstall", "com.github.uiautomator.test"])

        from uiautomator2 import init
        for (name, url) in init.app_uiautomator_apk_urls():
            apk_path = init.mirror_download(url)
            target_path = "/data/local/tmp/" + os.path.basename(apk_path)
            self.push(apk_path, target_path)
            logger.debug("pm install %s", target_path)
            self.shell(['pm', 'install', '-r', '-t', target_path])

    def sleep(self, seconds: float):
        """ same as time.sleep """
        time.sleep(seconds)

    def shell(self, cmdargs: Union[str, List[str]], stream=False, timeout=60):
        """
        Run adb shell command with arguments and return its output. Require atx-agent >=0.3.3

        Args:
            cmdargs: str or list, example: "ls -l" or ["ls", "-l"]
            timeout: seconds of command run, works on when stream is False
            stream: bool used for long running process.

        Returns:
            (output, exit_code) when stream is False
            requests.Response when stream is True, you have to close it after using

        Raises:
            RuntimeError

        For atx-agent is not support return exit code now.
        When command got something wrong, exit_code is always 1, otherwise exit_code is always 0
        """
        if isinstance(cmdargs, (list, tuple)):
            cmdline = list2cmdline(cmdargs)
        elif isinstance(cmdargs, str):
            cmdline = cmdargs
        else:
            raise TypeError("cmdargs type invalid", type(cmdargs))

        if stream:
            return self.http.get("/shell/stream",
                                 params={"command": cmdline},
                                 timeout=None,
                                 stream=True)
            # return self._request("get", "/shell/stream", params={"command": cmdline}, timeout=None, stream=True) # yapf: disable
        data = dict(command=cmdline, timeout=str(timeout))
        ret = self.http.post("/shell", data=data, timeout=timeout+10)
        if ret.status_code != 200:
            raise RuntimeError(
                "device agent responds with an error code %d" %
                ret.status_code, ret.text)
        resp = ret.json()
        exit_code = 1 if resp.get('error') else 0
        exit_code = resp.get('exitCode', exit_code)
        return ShellResponse(resp.get('output'), exit_code)

    @cached_property
    def http(self):
        return _AgentRequestSession(self)

    @property
    def info(self):
        return self.jsonrpc.deviceInfo(http_timeout=10)

    @property
    def wlan_ip(self):
        ip = self.http.get("/wlan/ip").text.strip()
        if not re.match(r"\d+\.\d+\.\d+\.\d+", ip):
            return None
        return ip

    #
    # app-uiautomator.apk jsonrpc methods
    #

    @property
    def _jsonrpc_url(self):
        return self._get_atx_agent_url() + "/jsonrpc/0"

    @property
    def jsonrpc(self):
        class JSONRpcWrapper():
            def __init__(self, server):
                self.server = server
                self.method = None

            def __getattr__(self, method):
                self.method = method  # jsonrpc function name
                return self

            def __call__(self, *args, **kwargs):
                http_timeout = kwargs.pop('http_timeout', HTTP_TIMEOUT)
                params = args if args else kwargs
                return self.server._jsonrpc_retry_call(self.method, params,
                                                       http_timeout)

        return JSONRpcWrapper(self)

    def _jsonrpc_retry_call(self, *args, **kwargs):
        try:
            return self._jsonrpc_call(*args, **kwargs)
        except (requests.ReadTimeout,
                ServerError,
                UiAutomationNotConnectedError) as e:
            self.reset_uiautomator(str(e))  # uiautomator可能出问题了，强制重启一下
        except (NullObjectExceptionError,
                NullPointerExceptionError,
                StaleObjectExceptionError) as e:
            logger.warning("jsonrpc call got: %s", str(e))
        return self._jsonrpc_call(*args, **kwargs)

    def _jsonrpc_call(self, method, params=[], http_timeout=60):
        """ jsonrpc2 call
        Refs:
            - http://www.jsonrpc.org/specification

        Raises:
            出现的错误一般有2大类:
                - JSONRPC服务端异常 ServerError
                - 远程方法返回的错误 RequestError
        """
        request_start = time.time()
        data = {
            "jsonrpc": "2.0",
            "id": self._jsonrpc_id(method),
            "method": method,
            "params": params,
        }
        data = json.dumps(data)
        res = self.http.post("/jsonrpc/0",
                             headers={"Content-Type": "application/json"},
                             data=data,
                             timeout=http_timeout)

        if res.status_code == 502:
            raise GatewayError(
                res, "gateway error, time used %.1fs" %
                (time.time() - request_start))
        if res.status_code == 410:  # http status gone: session broken
            raise SessionBrokenError("app quit or crash", res.text)
        if res.status_code != 200:
            raise BaseError(data, res.status_code, res.text,
                            "HTTP Return code is not 200", res.text)
        jsondata = res.json()
        error = jsondata.get('error')
        if not error:
            return jsondata.get('result')

        err = JSONRPCError(error, method)

        def is_exception(err, exception_name):
            return err.exception_name == exception_name or exception_name in err.message

        if isinstance(
                err.data,
                six.string_types) and 'UiAutomation not connected' in err.data:
            err.__class__ = UiAutomationNotConnectedError
        elif err.message:
            if is_exception(err, 'uiautomator.UiObjectNotFoundException'):
                err.__class__ = UiObjectNotFoundError
            elif is_exception(
                    err,
                    'android.support.test.uiautomator.StaleObjectException'):
                # StaleObjectException
                # https://developer.android.com/reference/android/support/test/uiautomator/StaleObjectException.html
                # A StaleObjectException exception is thrown when a UiObject2 is used after the underlying View has been destroyed.
                # In this case, it is necessary to call findObject(BySelector) to obtain a new UiObject2 instance.
                err.__class__ = StaleObjectExceptionError
            elif is_exception(err, 'java.lang.NullObjectException'):
                err.__class__ = NullObjectExceptionError
            elif is_exception(err, 'java.lang.NullPointerException'):
                err.__class__ = NullPointerExceptionError
        raise err

    def _jsonrpc_id(self, method):
        m = hashlib.md5()
        m.update(("%s at %f" % (method, time.time())).encode("utf-8"))
        return m.hexdigest()

    @property
    def uiautomator(self) -> _Service:
        return _Service("uiautomator", self)

    def _get_agent_version(self) -> Optional[str]:
        """ return None or atx-agent version """
        try:
            url = self.path2url("/version")
            # should not use self.http.get here
            r = requests.get(url, timeout=2)
            if r.status_code != 200:
                return None
            return r.text.strip()
        except requests.RequestException as e:
            return None
    
    def _is_agent_outdated(self) -> bool:
        version = self._get_agent_version()
        if version != __atx_agent_version__:
            return True
        return False

    def _is_agent_alive(self):
        return bool(self._get_agent_version())

    def _is_alive(self):
        try:
            r = self.http.post("/jsonrpc/0", timeout=2, retry=False, data=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "deviceInfo",
            }))
            if r.status_code != 200:
                return False
            if r.json().get("error"):
                return False
            return True
        except (requests.ReadTimeout, EnvironmentError):
            return False

    def reset_uiautomator(self, reason="unknown", depth=0):
        """
        Reset uiautomator

        Raises:
            RuntimeError

        Orders:
            - stop uiautomator keeper
            - am force-stop com.github.uiautomator
            - start uiautomator keeper(am instrument -w ...)
            - wait until uiautomator service is ready
        """
        if depth >= 2:
            raise EnvironmentError(
                "Uiautomator started failed.",
                reason,
                "https://github.com/openatx/uiautomator2/wiki/Common-issues",
                "adb shell am instrument -w -r -e debug false -e class com.github.uiautomator.stub.Stub com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner",
            )

        if depth > 0:
            logger.info("restart-uiautomator since \"%s\"", reason)

        # Note:
        # atx-agent check has moved to _AgentRequestSession
        # If code goes here, it means atx-agent is fine.

        if self._is_alive():
            return

        # atx-agent might be outdated, check atx-agent version here
        if self._is_agent_outdated():
            if self._serial: # update atx-agent will not work on WiFi
                self._prepare_atx_agent()

        ok = self._force_reset_uiautomator_v2(
            launch_test_app=depth > 0)  # uiautomator 2.0
        if ok:
            logger.info("uiautomator back to normal")
            return

        output = self._test_run_instrument()
        if "does not have a signature matching the target" in output:
            self._setup_uiautomator()
            reason = "signature not match, reinstall uiautomator apks"
        return self.reset_uiautomator(reason=reason,
                                      depth=depth + 1)

    def _force_reset_uiautomator_v2(self, launch_test_app=False):
        brand = self.shell("getprop ro.product.brand").output.strip()
        # logger.debug("Device: %s, %s", brand, self.serial)
        package_name = "com.github.uiautomator"

        self.uiautomator.stop()

        logger.debug("kill process(ps): uiautomator")
        self._kill_process_by_name("uiautomator")

        if self._is_apk_outdated():
            self._setup_uiautomator()

        if launch_test_app:
            self._grant_app_permissions()
            self.shell(['am', 'start', '-a', 'android.intent.action.MAIN', '-c',
                        'android.intent.category.LAUNCHER', '-n', package_name + "/" + ".ToastActivity"])
            
        self.uiautomator.start()

        # wait until uiautomator2 service is working
        time.sleep(.5)
        deadline = time.time() + 40.0  # in vivo-Y67, launch timeout 24s
        while time.time() < deadline:
            logger.debug("uiautomator-v2 is starting ... left: %.1fs",
                         deadline - time.time())

            if not self.uiautomator.running():
                break

            if self._is_alive():
                # 显示悬浮窗，增加稳定性
                # 可能会带来悬浮窗对话框
                # 目前先测试一下，之后需要改版一下
                if os.getenv("TMQ"):
                    self.show_float_window(True)
                return True
            time.sleep(1.0)

        self.uiautomator.stop()
        return False

    def _is_apk_outdated(self):
        # 检查被测应用是否存在
        apk_version = self._package_version("com.github.uiautomator")
        if apk_version is None:
            return True

        # 检查版本是否过期
        if apk_version < packaging.version.parse(__apk_version__):
            return True

        # 检查测试apk是否存在
        if self._package_version("com.github.uiautomator.test") is None:
            return True
        return False

    def _package_version(self, package_name: str) -> Optional[packaging.version.Version]:
        if self.shell(['pm', 'path', package_name]).exit_code != 0:
            return None
        dump_output = self.shell(['dumpsys', 'package', package_name]).output
        m = re.compile(r'versionName=(?P<name>[\d.]+)').search(dump_output)
        return packaging.version.parse(m.group('name') if m else "")

    def _grant_app_permissions(self):
        logger.debug("grant permissions")
        for permission in [
                "android.permission.SYSTEM_ALERT_WINDOW",
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.READ_PHONE_STATE",
        ]:
            self.shell(['pm', 'grant', "com.github.uiautomator", permission])

    def _test_run_instrument(self):
        shret = self.shell(
            "am instrument -w -r -e debug false -e class com.github.uiautomator.stub.Stub com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner",
            timeout=3)
        return shret.output

    def _kill_process_by_name(self, name, use_adb=False):
        for p in self._iter_process(use_adb=use_adb):
            if p.name == name and p.user == "shell":
                logger.debug("kill %s", name)
                kill_cmd = ["kill", "-9", str(p.pid)]
                if use_adb:
                    self._adb_device.shell(kill_cmd)
                else:
                    self.shell(kill_cmd)

    def _iter_process(self, use_adb=False):
        """
        List processes by cmd:ps

        Returns:
            list of Process(pid, name)
        """
        headers, pids = [], {}
        Header = None
        Process = namedtuple("Process", ["user", "pid", "name"])
        if use_adb:
            output = self._adb_device.shell("ps; ps -A")
        else:
            output = self.shell("ps; ps -A").output
        for line in output.splitlines():
            # USER PID ..... NAME
            fields = line.strip().split()
            if len(fields) < 3:
                continue
            if fields[0] == "USER":
                continue
            if not fields[1].isdigit():
                continue
            user, pid, name = fields[0], int(fields[1]), fields[-1]
            if pid in pids:
                continue
            pids[pid] = True
            yield Process(user, pid, name)

    def push(self, src, dst: str, mode=0o644, show_progress=False):
        """
        Push file into device

        Args:
            src (path or fileobj): source file
            dst (str): destination can be folder or file path

        Returns:
            dict object, for example:

                {"mode": "0660", "size": 63, "target": "/sdcard/ABOUT.rst"}

            Since chmod may fail in android, the result "mode" may not same with input args(mode)

        Raises:
            IOError(if push got something wrong)
        """
        modestr = oct(mode).replace('o', '')
        pathname = '/upload/' + dst.lstrip('/')
        filesize = 0
        if isinstance(src, six.string_types):
            if re.match(r"^https?://", src):
                r = requests.get(src, stream=True)
                if r.status_code != 200:
                    raise IOError(
                        "Request URL {!r} status_code {}".format(src, r.status_code))
                filesize = int(r.headers.get("Content-Length", "0"))
                fileobj = r.raw
            elif os.path.isfile(src):
                filesize = os.path.getsize(src)
                fileobj = open(src, 'rb')
            else:
                raise IOError("file {!r} not found".format(src))
        else:
            assert hasattr(src, "read")
            fileobj = src

        try:
            r = self.http.post(pathname,
                               data={'mode': modestr},
                               files={'file': fileobj})
            if r.status_code == 200:
                return r.json()
            raise IOError("push", "%s -> %s" % (src, dst), r.text)
        finally:
            fileobj.close()

    def pull(self, src: str, dst: str):
        """
        Pull file from device to local

        Raises:
            FileNotFoundError(py3) OSError(py2)

        Require atx-agent >= 0.0.9
        """
        pathname = "/raw/" + src.lstrip("/")
        r = self.http.get(pathname, stream=True)
        if r.status_code != 200:
            raise FileNotFoundError("pull", src, r.text)
        with open(dst, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
            if _mswindows:  # hotfix windows file size zero bug
                f.close()


class _Device(_BaseClient):
    __orientation = (  # device orientation
        (0, "natural", "n", 0), (1, "left", "l", 90),
        (2, "upsidedown", "u", 180), (3, "right", "r", 270))

    @property
    def debug(self) -> bool:
        return hasattr(self.http, 'debug') and self.http.debug

    @debug.setter
    def debug(self, value: bool):
        self.http.debug = bool(value)

    def set_new_command_timeout(self, timeout: int):
        """ default 3 minutes
        Args:
            timeout (int): seconds
        """
        r = self.http.post("/newCommandTimeout", data=str(int(timeout)))
        data = r.json()
        assert data['success'], data['description']
        logger.info("%s", data['description'])

    @cached_property
    def device_info(self):
        return self.http.get("/info").json()

    def window_size(self):
        """ return (width, height) """
        info = self.http.get('/info').json()
        w, h = info['display']['width'], info['display']['height']
        rotation = self._get_orientation()
        if (w > h) != (rotation % 2 == 1):
            w, h = h, w
        return w, h

    def _get_orientation(self):
        """
        Rotaion of the phone
        0: normal
        1: home key on the right
        2: home key on the top
        3: home key on the left
        """
        _DISPLAY_RE = re.compile(
            r'.*DisplayViewport{valid=true, .*orientation=(?P<orientation>\d+), .*deviceWidth=(?P<width>\d+), deviceHeight=(?P<height>\d+).*'
        )
        self.shell("dumpsys display")
        for line in self.shell(['dumpsys', 'display']).output.splitlines():
            m = _DISPLAY_RE.search(line, 0)
            if not m:
                continue
            # w = int(m.group('width'))
            # h = int(m.group('height'))
            o = int(m.group('orientation'))
            # w, h = min(w, h), max(w, h)
            return o
        return self.info["displayRotation"]

    @retry((IOError, SyntaxError), delay=.5, tries=5, jitter=0.1,
           max_delay=1, logger=logging)  # delay .5, .6, .7, .8 ...
    def screenshot(self, filename: Optional[str] = None, format="pillow"):
        """
        Take screenshot of device

        Returns:
            PIL.Image.Image, np.ndarray (OpenCV format) or None

        Args:
            filename (str): saved filename, if filename is set then return None
            format (str): used when filename is empty. one of ["pillow", "opencv", "raw"]

        Raises:
            IOError, SyntaxError, ValueError

        Examples:
            screenshot("saved.jpg")
            screenshot().save("saved.png")
            cv2.imwrite('saved.jpg', screenshot(format='opencv'))
        """
        r = self.http.get("/screenshot/0", timeout=10)
        if filename:
            with open(filename, 'wb') as f:
                f.write(r.content)
            return filename
        elif format == 'pillow':
            buff = io.BytesIO(r.content)
            try:
                return Image.open(buff).convert("RGB")
            except IOError as ex:
                # Always fail in secure page
                # 截图失败直接返回一个粉色的图片
                # d.settings['default_screenshot'] =
                if not self.settings['fallback_to_blank_screenshot']:
                    raise IOError("PIL.Image.open IOError", ex)
                return Image.new("RGB", self.window_size(), (220, 120, 100))
        elif format == 'opencv':
            import cv2
            import numpy as np
            nparr = np.fromstring(r.content, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif format == 'raw':
            return r.content
        else:
            raise ValueError("Invalid format {}".format(format))

    @retry(RetryError, delay=1.0, tries=2)
    def dump_hierarchy(self, compressed=False, pretty=False) -> str:
        """
        Args:
            shell (bool): use "adb shell uiautomator dump" to get hierarchy
            pretty (bool): format xml

        Same as
            content = self.jsonrpc.dumpWindowHierarchy(compressed, None)
        But through GET /dump/hierarchy will be more robust
        when dumpHierarchy fails, the atx-agent will restart uiautomator again, then retry

        v-1.3.4 change back to jsonrpc.dumpWindowHierarchy
        """
        content = self.jsonrpc.dumpWindowHierarchy(compressed, None)
        if content == "":
            raise RetryError("dump hierarchy is empty")

        if pretty and "\n " not in content:
            xml_text = xml.dom.minidom.parseString(content.encode("utf-8"))
            content = xml_text.decode('utf-8').toprettyxml(indent='  ')
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

        obj = self

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
            return self.touch.down(x, y).sleep(duration).up(x, y)

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
        rel2abs = self.pos_rel2abs
        fx, fy = rel2abs(fx, fy)
        tx, ty = rel2abs(tx, ty)
        if not duration:
            steps = SCROLL_STEPS
        if not steps:
            steps = int(duration * 200)
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
    def clipboard(self):
        return self.jsonrpc.getClipboard()

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

    def open_identify(self, theme='black'):
        """
        Args:
            theme (str): black or red
        """
        self.shell([
            'am', 'start', '-W', '-n',
            'com.github.uiautomator/.IdentifyActivity', '-e', 'theme', theme
        ])

    def __call__(self, **kwargs):
        return UiObject(self, Selector(**kwargs))


class _AppMixIn:
    def _pidof_app(self, package_name):
        """
        Return pid of package name
        """
        text = self.http.get('/pidof/' + package_name).text
        if text.isdigit():
            return int(text)

    @retry(OSError, delay=.3, tries=3, logger=logging)
    def app_current(self):
        """
        Returns:
            dict(package, activity, pid?)

        Raises:
            OSError

        For developer:
            Function reset_uiautomator need this function, so can't use jsonrpc here.
        """
        # Related issue: https://github.com/openatx/uiautomator2/issues/200
        # $ adb shell dumpsys window windows
        # Example output:
        #   mCurrentFocus=Window{41b37570 u0 com.incall.apps.launcher/com.incall.apps.launcher.Launcher}
        #   mFocusedApp=AppWindowToken{422df168 token=Token{422def98 ActivityRecord{422dee38 u0 com.example/.UI.play.PlayActivity t14}}}
        # Regexp
        #   r'mFocusedApp=.*ActivityRecord{\w+ \w+ (?P<package>.*)/(?P<activity>.*) .*'
        #   r'mCurrentFocus=Window{\w+ \w+ (?P<package>.*)/(?P<activity>.*)\}')
        _focusedRE = re.compile(
            r'mCurrentFocus=Window{.*\s+(?P<package>[^\s]+)/(?P<activity>[^\s]+)\}'
        )
        m = _focusedRE.search(self.shell(['dumpsys', 'window', 'windows'])[0])
        if m:
            return dict(package=m.group('package'),
                        activity=m.group('activity'))

        # try: adb shell dumpsys activity top
        _activityRE = re.compile(
            r'ACTIVITY (?P<package>[^\s]+)/(?P<activity>[^/\s]+) \w+ pid=(?P<pid>\d+)'
        )
        output, _ = self.shell(['dumpsys', 'activity', 'top'])
        ms = _activityRE.finditer(output)
        ret = None
        for m in ms:
            ret = dict(package=m.group('package'),
                       activity=m.group('activity'),
                       pid=int(m.group('pid')))
        if ret:  # get last result
            return ret
        raise OSError("Couldn't get focused app")

    def app_install(self, data):
        """
        Args:
            data: can be file path or url or file object

        Raises:
            RuntimeError
        """
        target = "/data/local/tmp/_tmp.apk"
        self.push(data, target, show_progress=True)
        logger.debug("pm install -rt %s", target)
        ret = self.shell(['pm', 'install', "-r", "-t", target])
        if ret.exit_code != 0:
            raise RuntimeError(ret.output, ret.exit_code)

    def wait_activity(self, activity, timeout=10):
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

        if use_monkey:
            self.shell([
                'monkey', '-p', package_name, '-c',
                'android.intent.category.LAUNCHER', '1'
            ])
            if wait:
                self.app_wait(package_name)
            return

        if not activity:
            info = self.app_info(package_name)
            activity = info['mainActivity']
            if activity.find(".") == -1:
                activity = "." + activity

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
                    break
            else:
                if package_name in self.app_list_running():
                    pid = self._pidof_app(package_name)
                    break
            time.sleep(1)

        return pid or 0

    def app_list(self, filter: str = None) -> list:
        """
        Args:
            filter: [-f] [-d] [-e] [-s] [-3] [-i] [-u] [--user USER_ID] [FILTER]
        Returns:
            list of apps by filter
        """
        output, _ = self.shell(['pm', 'list', 'packages', filter])
        packages = re.findall(r'package:([^\s]+)', output)
        return list(packages)

    def app_list_running(self) -> list:
        """
        Returns:
            list of running apps
        """
        output, _ = self.shell(['pm', 'list', 'packages'])
        packages = re.findall(r'package:([^\s]+)', output)
        process_names = re.findall(r'([^\s]+)$',
                                   self.shell('ps; ps -A').output, re.M)
        return list(set(packages).intersection(process_names))

    def app_stop(self, package_name):
        """ Stop one application: am force-stop"""
        self.shell(['am', 'force-stop', package_name])

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
        self.shell(['pm', 'clear', package_name])

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

    def app_info(self, package_name: str):
        """
        Get app info

        Args:
            package_name (str): package name

        Return example:
            {
                "mainActivity": "com.github.uiautomator.MainActivity",
                "label": "ATX",
                "versionName": "1.1.7",
                "versionCode": 1001007,
                "size":1760809
            }

        Raises:
            UiaError
        """
        resp = self.http.get(f"/packages/{package_name}/info")
        resp.raise_for_status()
        resp = resp.json()
        if not resp.get('success'):
            raise BaseError(resp.get('description', 'unknown'))
        return resp.get('data')

    def app_icon(self, package_name: str):
        """
        Returns:
            PIL.Image

        Raises:
            UiaError
        """
        url = f'/packages/{package_name}/icon'
        resp = self.http.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))


class _DeprecatedMixIn:
    @property
    # @deprecated(version="2.0.0", reason="You should use app_current instead")
    def address(self):
        return self._get_atx_agent_url()

    @deprecated(version="3.0.0", reason="You should use d.uiautomator.start() instead")
    def service(self, name):
        # just do not care about the name
        return self.uiautomator

    @deprecated(version="3.0.0", reason="You should use app_current instead")
    def current_app(self):
        return self.app_current()

    @property
    def wait_timeout(self):  # wait element timeout
        return self.settings['wait_timeout']

    @wait_timeout.setter
    @deprecated(version="3.0.0", reason="You should use implicitly_wait instead")
    def wait_timeout(self, v: Union[int, float]):
        self.settings['wait_timeout'] = v

    @property
    @deprecated(version="3.0.0", reason="This method will deprecated soon")
    def agent_alive(self):
        return self._is_agent_alive()

    @property
    @deprecated(version="3.0.0")
    def alive(self):
        return self._is_alive()

    @deprecated(version="3.0.0", reason="method: healthcheck is useless now")
    def healthcheck(self):
        self.reset_uiautomator("healthcheck")

    @deprecated(version="3.0.0", reason="method: session is useless now")
    def session(self, package_name=None, attach=False, launch_timeout=None, strict=False):
        if package_name is None:
            return self

        if not attach:
            request_data = {"flags": "-S"}
            if launch_timeout:
                request_data["timeout"] = str(launch_timeout)
            resp = self.http.post("/session/" + package_name,
                                  data=request_data)
            if resp.status_code == 410:  # Gone
                raise SessionBrokenError(package_name, resp.text)
            resp.raise_for_status()
            jsondata = resp.json()
            if not jsondata["success"]:
                raise SessionBrokenError("app launch failed",
                                         jsondata["error"], jsondata["output"])

            time.sleep(2.5)  # wait launch finished, maybe no need
        pid = self._pidof_app(package_name)
        if not pid:
            if strict:
                raise SessionBrokenError(package_name)
            return self.session(package_name,
                                attach=False,
                                launch_timeout=launch_timeout)
        return self

    @property
    def click_post_delay(self):
        """ Deprecated or not deprecated, this is a question """
        return self.settings['post_delay']

    @click_post_delay.setter
    def click_post_delay(self, v: Union[int, float]):
        self.settings['post_delay'] = v

    @deprecated(version="2.0.0", reason="use d.toast.show(text, duration) instead")
    def make_toast(self, text, duration=1.0):
        """ Show toast
        Args:
            text (str): text to show
            duration (float): seconds of display
        """
        return self.jsonrpc.makeToast(text, duration * 1000)

    def unlock(self):
        """ unlock screen """
        if not self.info['screenOn']:
            self.press("power")
            self.swipe(0.1, 0.9, 0.9, 0.1)


class _InputMethodMixIn:
    def set_fastinput_ime(self, enable: bool = True):
        """ Enable of Disable FastInputIME """
        fast_ime = 'com.github.uiautomator/.FastInputIME'
        if enable:
            self.shell(['ime', 'enable', fast_ime])
            self.shell(['ime', 'set', fast_ime])
        else:
            self.shell(['ime', 'disable', fast_ime])

    def send_keys(self, text: str, clear: bool = False):
        """
        Args:
            text (str): text to set
            clear (bool): clear before set text

        Raises:
            EnvironmentError
        """
        try:
            self.wait_fastinput_ime()
            btext = text.encode('utf-8')
            base64text = base64.b64encode(btext).decode()
            cmd = "ADB_SET_TEXT" if clear else "ADB_INPUT_TEXT"
            self.shell(
                ['am', 'broadcast', '-a', cmd, '--es', 'text', base64text])
            return True
        except EnvironmentError:
            warnings.warn(
                "set FastInputIME failed. use \"d(focused=True).set_text instead\"",
                Warning)
            return self(focused=True).set_text(text)
            # warnings.warn("set FastInputIME failed. use \"adb shell input text\" instead", Warning)
            # self.shell(["input", "text", text.replace(" ", "%s")])

    def send_action(self, code):
        """
        Simulate input method edito code

        Args:
            code (str or int): input method editor code

        Examples:
            send_action("search"), send_action(3)

        Refs:
            https://developer.android.com/reference/android/view/inputmethod/EditorInfo
        """
        self.wait_fastinput_ime()
        __alias = {
            "go": 2,
            "search": 3,
            "send": 4,
            "next": 5,
            "done": 6,
            "previous": 7,
        }
        if isinstance(code, six.string_types):
            code = __alias.get(code, code)
        self.shell([
            'am', 'broadcast', '-a', 'ADB_EDITOR_CODE', '--ei', 'code',
            str(code)
        ])

    def clear_text(self):
        """ clear text
        Raises:
            EnvironmentError
        """
        try:
            self.wait_fastinput_ime()
            self.shell(['am', 'broadcast', '-a', 'ADB_CLEAR_TEXT'])
        except EnvironmentError:
            # for Android simulator
            self(focused=True).clear_text()

    def wait_fastinput_ime(self, timeout=5.0):
        """ wait FastInputIME is ready
        Args:
            timeout(float): maxium wait time

        Raises:
            EnvironmentError
        """
        if not self.serial:  # maybe simulator eg: genymotion, 海马玩模拟器
            raise EnvironmentError("Android simulator is not supported.")

        deadline = time.time() + timeout
        while time.time() < deadline:
            ime_id, shown = self.current_ime()
            if ime_id != "com.github.uiautomator/.FastInputIME":
                self.set_fastinput_ime(True)
                time.sleep(0.5)
                continue
            if shown:
                return True
            time.sleep(0.2)
        raise EnvironmentError("FastInputIME started failed")

    def current_ime(self):
        """ Current input method
        Returns:
            (method_id(str), shown(bool)

        Example output:
            ("com.github.uiautomator/.FastInputIME", True)
        """
        _INPUT_METHOD_RE = re.compile(r'mCurMethodId=([-_./\w]+)')
        dim, _ = self.shell(['dumpsys', 'input_method'])
        m = _INPUT_METHOD_RE.search(dim)
        method_id = None if not m else m.group(1)
        shown = "mInputShown=true" in dim
        return (method_id, shown)


class _PluginMixIn:
    @cached_property
    def settings(self) -> Settings:
        return Settings(self)

    def watch_context(self, autostart: bool = True, builtin: bool = False) -> WatchContext:
        wc = WatchContext(self, builtin=builtin)
        if autostart:
            wc.start()
        return wc

    @cached_property
    def watcher(self) -> Watcher:
        return Watcher(self)

    @cached_property
    def xpath(self) -> xpath.XPath:
        return xpath.XPath(self)

    @cached_property
    def taobao(self):
        try:
            import uiautomator2_taobao as tb
        except ImportError:
            raise RuntimeError(
                "This method can only use inside alibaba network")
        return tb.Taobao(self)

    @cached_property
    def alibaba(self):
        try:
            import uiautomator2_taobao as tb
        except ImportError:
            raise RuntimeError(
                "This method can only use inside alibaba network")
        return tb.Alibaba(self)

    @cached_property
    def image(self):
        from uiautomator2 import image as _image
        return _image.ImageX(self)

    @cached_property
    def screenrecord(self):
        from uiautomator2 import screenrecord as _sr
        return _sr.Screenrecord(self)

    @cached_property
    def widget(self):
        from uiautomator2.widget import Widget
        return Widget(self)

    @cached_property
    def swipe_ext(self) -> SwipeExt:
        return SwipeExt(self)

    # def _find_element(self, xpath: str, _class=None, pos=None, activity=None, package=None):
    #    raise NotImplementedError()

    # def __getattr__(self, attr):
    #     if attr in self._cached_plugins:
    #         return self._cached_plugins[attr]
    #     if attr.startswith('ext_'):
    #         plugin_name = attr[4:]
    #         if plugin_name not in self.__plugins:
    #             raise ValueError("plugin \"%s\" not registed" %
    #                                  plugin_name)
    #         func, args, kwargs = self.__plugins[plugin_name]
    #         obj = functools.partial(func, self)(*args, **kwargs)
    #         self._cached_plugins[attr] = obj
    #         return obj
    #     try:
    #         return getattr(self._default_session, attr)
    #     except AttributeError:
    #         raise AttributeError(
    #             "'Session or Device' object has no attribute '%s'" % attr)


class Device(_Device, _AppMixIn, _PluginMixIn, _InputMethodMixIn, _DeprecatedMixIn):
    """ Device object """


# for compatible with old code
Session = Device


def _fix_wifi_addr(addr: str) -> Optional[str]:
    if not addr:
        return None
    if re.match(r"^https?://", addr):  # eg: http://example.org
        return addr

    # make a request
    # eg: 10.0.0.1, 10.0.0.1:7912
    if ':' not in addr:
        addr += ":7912"  # make default port 7912
    try:
        r = requests.get("http://" + addr + "/version", timeout=2)
        r.raise_for_status()
        return "http://" + addr
    except:
        return None


def connect(addr=None) -> Device:
    """
    Args:
        addr (str): uiautomator server address or serial number. default from env-var ANDROID_DEVICE_IP

    Returns:
        Device

    Raises:
        ConnectError

    Example:
        connect("10.0.0.1:7912")
        connect("10.0.0.1") # use default 7912 port
        connect("http://10.0.0.1")
        connect("http://10.0.0.1:7912")
        connect("cff1123ea")  # adb device serial number
    """
    if not addr or addr == '+':
        addr = os.getenv('ANDROID_DEVICE_IP') or os.getenv("ANDROID_SERIAL")
    wifi_addr = _fix_wifi_addr(addr)
    if wifi_addr:
        return connect_wifi(addr)
    return connect_usb(addr)


def connect_adb_wifi(addr) -> Device:
    """
    Run adb connect, and then call connect_usb(..)

    Args:
        addr: ip+port which can be used for "adb connect" argument

    Raises:
        ConnectError
    """
    assert isinstance(addr, six.string_types)

    subprocess.call([adbutils.adb_path(), "connect", addr])
    try:
        subprocess.call([adbutils.adb_path(), "-s", addr, "wait-for-device"],
                        timeout=2)
    except subprocess.TimeoutExpired:
        raise ConnectError("Fail execute", "adb connect " + addr)
    return connect_usb(addr)


def connect_usb(serial: Optional[str] = None, init: bool = False) -> Device:
    """
    Args:
        serial (str): android device serial

    Returns:
        Device

    Raises:
        ConnectError
    """
    if init:
        logger.warning("connect_usb, args init=True is deprecated since 2.8.0")

    if not serial:
        device = adbutils.adb.device()
        serial = device.serial
    return Device(serial)


def connect_wifi(addr: str) -> Device:
    """
    Args:
        addr (str) uiautomator server address.

    Returns:
        Device

    Raises:
        ConnectError

    Examples:
        connect_wifi("10.0.0.1")
    """
    _addr = _fix_wifi_addr(addr)
    if _addr is None:
        raise ConnectError("addr is invalid or atx-agent is not running", addr)
    del addr
    return Device(_addr)
