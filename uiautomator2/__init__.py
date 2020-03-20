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

import functools
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import warnings
from collections import namedtuple
from datetime import datetime
from typing import Optional, Union

import humanize
import progress.bar
import requests
import six
import six.moves.urllib.parse as urlparse
from retry import retry
from urllib3.util.retry import Retry

import adbutils
from deprecated import deprecated
from logzero import logger

from . import xpath
from .utils import list2cmdline
from .exceptions import (BaseError, ConnectError, GatewayError, JsonRpcError,
                         NullObjectExceptionError, NullPointerExceptionError,
                         SessionBrokenError, StaleObjectExceptionError,
                         UiaError, UiAutomationNotConnectedError,
                         UiObjectNotFoundError)
from .init import Initer
from .session import Session, set_fail_prompt  # noqa: F401
from .utils import cache_return
from .version import __atx_agent_version__
from .settings import Settings
from .watcher import Watcher

if six.PY2:
    FileNotFoundError = OSError

DEBUG = False
HTTP_TIMEOUT = 60


class _ProgressBar(progress.bar.Bar):
    message = "progress"
    suffix = '%(percent)d%% [%(eta_td)s, %(speed)s]'

    @property
    def speed(self):
        return humanize.naturalsize(self.elapsed and self.index / self.elapsed,
                                    gnu=True) + '/s'


def log_print(s):
    thread_name = threading.current_thread().getName()
    print(thread_name + ": " + datetime.now().strftime('%H:%M:%S,%f')[:-3] +
          " " + s)


def fix_wifi_addr(addr: str) -> Optional[str]:
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


def connect(addr=None):
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
    wifi_addr = fix_wifi_addr(addr)
    if wifi_addr:
        return connect_wifi(addr)
    return connect_usb(addr)


def connect_adb_wifi(addr):
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


def connect_usb(serial=None, healthcheck=False, init=False):
    """
    Args:
        serial (str): android device serial

    Returns:
        Device

    Raises:
        ConnectError
    """

    adb = adbutils.AdbClient()
    if not serial:
        device = adb.device()
        serial = device.serial

    d = Device()
    d._connect_method = "usb"
    d._serial = serial
    d._init_atx_agent()

    if healthcheck:
        warnings.warn("healthcheck param is deprecated", DeprecationWarning)
    if init:
        warnings.warn("init param is deprecated", DeprecationWarning)
    return d


def connect_wifi(addr: str) -> "Device":
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
    if not re.match(r"^https?://", addr):
        addr = "http://" + addr
    # fixed_addr = fix_wifi_addr(addr)
    # if fixed_addr is None:
    # raise ConnectError("addr is invalid or atx-agent is not running", addr)
    u = urlparse.urlparse(addr)
    host = u.hostname
    port = u.port or 7912
    d = Device(host, port)
    d._connect_method = "wifi"
    return d


class TimeoutRequestsSession(requests.Session):
    def __init__(self):
        super(TimeoutRequestsSession, self).__init__()
        retries = Retry(total=3, connect=3, backoff_factor=0.5)
        # refs: https://stackoverflow.com/questions/33895739/python-requests-cant-load-any-url-remote-end-closed-connection-without-respo
        # refs: https://stackoverflow.com/questions/15431044/can-i-set-max-retries-for-requests-request
        adapter = requests.adapters.HTTPAdapter(max_retries=retries)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        if 'timeout' not in kwargs:
            kwargs['timeout'] = HTTP_TIMEOUT
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


def plugin_register(name, plugin, *args, **kwargs):
    """
    Add plugin into Device

    Args:
        name: string
        plugin: class or function which take d as first parameter

    Example:
        def upload_screenshot(d):
            def inner():
                d.screenshot("tmp.jpg")
                # use requests.post upload tmp.jpg
            return inner

        plugin_register("upload_screenshot", save_screenshot)

        d = u2.connect()
        d.ext_upload_screenshot()
    """
    Device.plugins()[name] = (plugin, args, kwargs)


def plugin_clear():
    Device.plugins().clear()


class Device(object):
    __isfrozen = False
    __plugins = {}

    def __init__(self, host="127.0.0.1", port=7912):
        """
        Args:
            host (str): host address
            port (int): port number

        Raises:
            EnvironmentError
        """
        self._host = host
        self._port = port
        self._adb_device = None  # adbutils.Device
        self._serial = None
        self._connect_method = None
        self._reqsess = TimeoutRequestsSession(
        )  # use Session to enable HTTP Keep-Alive
        self._default_session = Session(self, None)
        self._cached_plugins = {}
        self._hooks = {}
        self._atx_agent_path = "/data/local/tmp/atx-agent"

        self.__devinfo = None
        self.__uiautomator_failed = False
        self.__uiautomator_lock = threading.Lock()

        self.platform = None  # hot fix for weditor

        self.ash = AdbShell(self.shell)  # the powerful adb shell
        self._freeze()  # prevent creating new attrs

    def _freeze(self):
        self.__isfrozen = True

    def request_agent(self, relative_url: str, method="get", timeout=60.0):
        """ send http-request to atx-agent """
        return self._reqsess.request(method, relative_url, timeout=timeout)

    def _init_atx_agent(self, start_uiautomator=False):
        """
        Install atx-agent and app-uiautomator apks, only usb connected device is ok
        """
        if self._connect_method != "usb":
            raise ConnectError("http connection is down")

        assert self._connect_method == "usb"
        assert self._serial

        self._adb_device = self.__wait_for_device(self._serial)
        if not self._adb_device:
            raise RuntimeError("USB device %s is offline" % self._serial)

        ad = self._adb_device
        lport = ad.forward_port(7912)
        self._port = lport

        if self.agent_alive and self.alive:
            return

        initer = Initer(ad)
        if not initer.check_install():
            initer.install()  # same as run cli: uiautomator2 init

        if not self.agent_alive:
            self.__start_atx_agent()

        if start_uiautomator:
            if not self.alive:
                self.reset_uiautomator("atx-agent restarted")

    def __wait_for_device(self, serial: str, timeout=70.0):
        """
        wait for device came online
        """
        deadline = time.time() + timeout
        first = True

        while time.time() < deadline:
            device = None
            for d in adbutils.adb.device_list():
                if d.serial == serial:
                    device = d
                    break

            if device:
                if not first:
                    logger.info("device(%s) came online", serial)
                return device

            if first:
                first = False
            else:
                logger.info("wait for device(%s), left(%.1fs)", serial,
                            deadline - time.time())

            time.sleep(2.0)
        return None

    def __start_atx_agent(self):
        warnings.warn("start atx-agent ...", RuntimeWarning)
        # TODO: /data/local/tmp might not be execuable and atx-agent can be somewhere else
        ad = self._adb_device
        ad.shell([self._atx_agent_path, "server", "--stop"])
        ad.shell([self._atx_agent_path, "server", "--nouia", "-d"])
        deadline = time.time() + 3
        while time.time() < deadline:
            if self.agent_alive:
                return
        raise RuntimeError("atx-agent recover failed")

    @property
    def _server_url(self):
        return 'http://{}:{}'.format(self._host, self._port)

    @property
    def jsonrpc_url(self):
        return self._server_url + "/jsonrpc/0"

    def _request(self, method: str, url: str, reconnect=True, **kwargs):
        """ make http request with reconnect
        Args:
            method (str): get, put, delete or post
            url: request url
            reconnect (bool): default True
        """
        try:
            return self._reqsess.request(method, self.path2url(url), **kwargs)
        except requests.ConnectionError:
            if not reconnect:
                raise
            self._init_atx_agent()
            return self._reqsess.request(method, self.path2url(url), **kwargs)

    # for compatible with old version
    @property
    def wait_timeout(self):  # wait element timeout
        return self.settings['wait_timeout']

    @wait_timeout.setter
    def wait_timeout(self, v: Union[int, float]):
        self.settings['wait_timeout'] = v

    @property
    def click_post_delay(self):
        return self.settings['post_delay']

    @click_post_delay.setter
    def click_post_delay(self, v: Union[int, float]):
        self.settings['post_delay'] = v

    # end of compatible code

    @property
    def debug(self):
        return hasattr(self._reqsess, 'debug') and self._reqsess.debug

    @debug.setter
    def debug(self, value):
        self._reqsess.debug = bool(value)

    @staticmethod
    def plugins():
        return Device.__plugins

    def __setattr__(self, key, value):
        """ Prevent creating new attributes outside __init__ """
        if self.__isfrozen and not hasattr(self, key):
            raise TypeError("Key %s does not exist in class %r" % (key, self))
        object.__setattr__(self, key, value)

    def __str__(self):
        return 'uiautomator2 object for %s:%d' % (self._host, self._port)

    def __repr__(self):
        return str(self)

    @property
    def serial(self):
        if not self._serial:
            self._serial = self.shell('getprop ro.serialno').output.strip()
        return self._serial

    @property
    def address(self):
        return f"http://{self._host}:{self._port}"

    @property
    def jsonrpc(self):
        """
        Make jsonrpc call easier
        For example:
            self.jsonrpc.pressKey("home")
        """
        return self.setup_jsonrpc()

    def path2url(self, path: str):
        if re.match(r"^https?://", path):
            return path
        return urlparse.urljoin(self._server_url, path)

    def window_size(self):
        """ return (width, height) """
        info = self._request("get", '/info').json()
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

    def hooks_register(self, func):
        """
        Args:
            func: should accept 3 args. func_name:string, args:tuple, kwargs:dict
        """
        self._hooks[func] = True

    def hooks_apply(self, stage, func_name, args=(), kwargs={}, ret=None):
        """
        Args:
            stage(str): one of "before" or "after"
        """
        for fn in self._hooks.keys():
            fn(stage, func_name, args, kwargs, ret)

    def setup_jsonrpc(self, jsonrpc_url=None):
        """
        Wrap jsonrpc call into object
        Usage example:
            self.setup_jsonrpc().pressKey("home")
        """

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
                return self.server.jsonrpc_retry_call(self.method, params,
                                                      http_timeout)

        return JSONRpcWrapper(self)

    def jsonrpc_retry_call(self, *args, **kwargs):
        try:
            return self.jsonrpc_call(*args, **kwargs)
        except (GatewayError, ):
            warnings.warn(
                "uiautomator2 is not reponding, restart uiautomator2 automatically",
                RuntimeWarning,
                stacklevel=1)
            self.reset_uiautomator("UiAutomator stopped")
        except requests.ReadTimeout as e:
            self.reset_uiautomator("Http read-timeout: " + str(e))
        except UiAutomationNotConnectedError:
            self.reset_uiautomator("UiAutomation not connected")
        except (NullObjectExceptionError, NullPointerExceptionError,
                StaleObjectExceptionError) as e:
            if args[1] != 'dumpWindowHierarchy':  # args[1] method
                warnings.warn(
                    "uiautomator2 raise exception %s, and run code again" % e,
                    RuntimeWarning,
                    stacklevel=1)
            time.sleep(1)
        except requests.ConnectionError:
            logger.info(
                "Device connection is not stable, rerun init-atx-agent ...")
            if self._connect_method == "usb":
                self._init_atx_agent()
            else:
                raise

        return self.jsonrpc_call(*args, **kwargs)

    def jsonrpc_call(self, method, params=[], http_timeout=60):
        """ jsonrpc2 call
        Refs:
            - http://www.jsonrpc.org/specification
        """
        jsonrpc_url = self.jsonrpc_url
        request_start = time.time()
        data = {
            "jsonrpc": "2.0",
            "id": self._jsonrpc_id(method),
            "method": method,
            "params": params,
        }
        data = json.dumps(data)
        res = self._request(
            "post",
            jsonrpc_url,  # +"?m="+method, #?method is for debug
            headers={"Content-Type": "application/json"},
            timeout=http_timeout,
            data=data)
        if DEBUG:
            print("Shell$ curl -X POST -d '{}' {}".format(data, jsonrpc_url))
            print("Output> " + res.text)
        if res.status_code == 502:
            raise GatewayError(
                res, "gateway error, time used %.1fs" %
                (time.time() - request_start))
        if res.status_code == 410:  # http status gone: session broken
            raise SessionBrokenError("app quit or crash", jsonrpc_url,
                                     res.text)
        if res.status_code != 200:
            raise BaseError(jsonrpc_url, data, res.status_code, res.text,
                            "HTTP Return code is not 200", res.text)
        jsondata = res.json()
        error = jsondata.get('error')
        if not error:
            return jsondata.get('result')

        # error happends
        err = JsonRpcError(error, method)

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
    def agent_alive(self):
        try:
            r = self._request("get", '/version', timeout=2, reconnect=False)
            if r.status_code == 200:
                return True
        except (requests.HTTPError, requests.ConnectionError) as e:
            return False

    @property
    def alive(self):
        try:
            r = self._request("post",
                              '/jsonrpc/0',
                              data=json.dumps({
                                  "jsonrpc": "2.0",
                                  "id": 1,
                                  "method": "deviceInfo"
                              }),
                              timeout=2,
                              reconnect=False)
            if r.status_code != 200:
                return False
            if r.json().get('error'):
                # logger.debug("alive error:", r.json().get('error'))
                return False
            return True
        except requests.exceptions.ReadTimeout:
            return False
        except EnvironmentError:
            return False

    def _kill_process_by_name(self, name):
        for p in self._iter_process():
            if p.name == name and p.user == "shell":
                logger.debug("kill uiautomator")
                self.shell(["kill", "-9", str(p.pid)])

    def service(self, name):
        """ Manage service start or stop

        Example:
            d.service("uiautomator").start()
            d.service("uiautomator").stop()
        """
        u2obj = self

        class _Service(object):
            def __init__(self, name):
                self.name = name
                # FIXME(ssx): support other service: minicap, minitouch
                assert name == 'uiautomator'
                self.service_url = u2obj.path2url("/services/" + name)

            def raise_for_status(self, res):
                if res.status_code != 200:
                    if res.headers['content-type'].startswith(
                            "application/json"):
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
                res = u2obj._reqsess.post(self.service_url)
                self.raise_for_status(res)

            def stop(self):
                """
                1. stop command which launched with uiautomator 1.0
                    Eg: adb shell uiautomator runtest androidUiAutomator.jar
                """
                res = u2obj._reqsess.delete(self.service_url)
                self.raise_for_status(res)

            def running(self) -> bool:
                res = u2obj._reqsess.get(self.service_url)
                self.raise_for_status(res)
                return res.json().get("running")

        return _Service(name)

    @property
    def uiautomator(self):
        return self.service("uiautomator")

    def set_new_command_timeout(self, timeout: int):
        """ default 3 minutes
        Args:
            timeout (int): seconds
        """
        r = self._request("post", "/newCommandTimeout", data=str(int(timeout)))
        data = r.json()
        assert data['success'], data['description']
        logger.info("%s", data['description'])

    def reset_uiautomator(self, reason="unknown"):
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
        logger.debug("restart-uiautomator since \"%s\"", reason)
        with self.__uiautomator_lock:
            if self.alive:
                return
            ok = self._force_reset_uiautomator_v2()  # uiautomator 2.0
            if not ok:
                shret = self.shell(
                    "am instrument -w -r -e debug false -e class com.github.uiautomator.stub.Stub com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner",
                    timeout=3)
                if "does not have a signature matching the target " in shret.output:
                    raise RuntimeError(
                        "com.github.uiautomator does not have a signature matching the target com.github.uiautomator.test, please reinstall apks"
                    )
                if not self._force_reset_uiautomator_v2(launch_test_app=True):
                    raise EnvironmentError(
                        "Uiautomator started failed.",
                        "https://github.com/openatx/uiautomator2/wiki/Common-issues",
                        "adb shell am instrument -w -r -e debug false -e class com.github.uiautomator.stub.Stub com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner",
                        shret.output)

            logger.info("uiautomator back to normal")

    def _force_reset_uiautomator_v1(self):
        """ uiautomator v1 only need bundle.jar and uiautomator-stub.jar

        Refs:
            https://github.com/openatx/android-uiautomator-jsonrpcserver
        """
        self.uiautomator.start()
        deadline = time.time() + 20.0
        while time.time() < deadline:
            logger.debug("uiautomator(1.0) is starting ...")
            if self.alive:
                return True
            time.sleep(1)
        return False

    def _grant_app_permissions(self):
        logger.debug("grant permissions")
        for permission in [
                "android.permission.SYSTEM_ALERT_WINDOW",
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.READ_PHONE_STATE",
        ]:
            self.shell(['pm', 'grant', "com.github.uiautomator", permission])

    def _show_float_window(self, show=True):
        """ 显示悬浮窗，提高uiautomator运行的稳定性 """
        arg = "true" if show else "false"
        self.shell([
            "am", "start", "-n", "com.github.uiautomator/.ToastActivity", "-e",
            "showFloatWindow", arg
        ])

    def _force_reset_uiautomator_v2(self, launch_test_app=False):
        brand = self.shell("getprop ro.product.brand").output.strip()
        logger.debug("Device: %s, %s", brand, self.serial)
        package_name = "com.github.uiautomator"

        self.uiautomator.stop()

        #self.shell(["am", "force-stop", package_name])
        #logger.debug("stop app: %s", package_name)

        # stop command which launched with uiautomator 1.0
        # eg: adb shell uiautomator runtest androidUiAutomator.jar
        logger.debug("kill process(ps): uiautomator")
        self._kill_process_by_name("uiautomator")

        if launch_test_app:
            self._grant_app_permissions()
            self.app_start(package_name,
                           ".ToastActivity")  # -e showFloatWindow true
        self.uiautomator.start()

        # wait until uiautomator2 service is working
        time.sleep(.5)
        deadline = time.time() + 40.0  # in vivo-Y67, launch timeout 24s
        while time.time() < deadline:
            logger.debug("uiautomator-v2 is starting ... left: %.1fs",
                         deadline - time.time())

            if not self.uiautomator.running():
                break

            if self.alive:
                return True
            time.sleep(1.0)

        self.uiautomator.stop()
        return False

    def healthcheck(self):
        """
        Reset device into health state

        Raises:
            RuntimeError
        """
        sh = self.ash
        if not sh.is_screen_on():
            print(time.strftime("[%Y-%m-%d %H:%M:%S]"), "wakeup screen")
            sh.keyevent("WAKEUP")
            sh.keyevent("HOME")
            sh.swipe(0.1, 0.9, 0.9, 0.1)  # swipe to unlock

        sh.keyevent("HOME")
        sh.keyevent("BACK")
        self.reset_uiautomator("healthcheck")

    def app_install(self, url, installing_callback=None, server=None):
        """
        {u'message': u'downloading', "progress": {u'totalSize': 407992690, u'copiedSize': 49152}}

        Returns:
            packageName

        Raises:
            RuntimeError
        """
        r = self._request("post", '/install', data={'url': url})
        if r.status_code != 200:
            raise RuntimeError("app install error:", r.text)
        id = r.text.strip()
        print(time.strftime('%H:%M:%S'), "id:", id)
        return self._wait_install_finished(id, installing_callback)

    def _wait_install_finished(self, id, installing_callback):
        bar = None
        downloaded = True

        while True:
            resp = self._request("get", '/install/' + id)
            resp.raise_for_status()
            jdata = resp.json()
            message = jdata['message']
            pg = jdata.get('progress')

            def notty_print_progress(pg):
                written = pg['copiedSize']
                total = pg['totalSize']
                print(
                    time.strftime('%H:%M:%S'), 'downloading %.1f%% [%s/%s]' %
                    (100.0 * written / total if total != 0 else 0,
                     humanize.naturalsize(written, gnu=True),
                     humanize.naturalsize(total, gnu=True)))

            if message == 'downloading':
                downloaded = False
                if pg:  # if there is a progress
                    if hasattr(sys.stdout, 'isatty'):
                        if sys.stdout.isatty():
                            if not bar:
                                bar = _ProgressBar(time.strftime('%H:%M:%S') +
                                                   ' downloading',
                                                   max=pg['totalSize'])
                            written = pg['copiedSize']
                            bar.next(written - bar.index)
                        else:
                            notty_print_progress(pg)
                    else:
                        pass
                else:
                    print(time.strftime('%H:%M:%S'), "download initialing")
            else:
                if not downloaded:
                    downloaded = True
                    if bar:  # bar only set in atty
                        bar.next(pg['copiedSize'] - bar.index) if pg else None
                        bar.finish()
                    else:
                        print(time.strftime('%H:%M:%S'), "download 100%")
                print(time.strftime('%H:%M:%S'), message)
            if message == 'installing':
                if callable(installing_callback):
                    installing_callback(self)
            if message == 'success installed':
                return jdata.get('packageName')

            if jdata.get('error'):
                raise RuntimeError("error", jdata.get('error'))

            try:
                time.sleep(1)
            except KeyboardInterrupt:
                bar.finish() if bar else None
                print("keyboard interrupt catched, cancel install id", id)
                self._request("delete", '/install/' + id)
                raise

    def shell(self, cmdargs, stream=False, timeout=60):
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
        cmdline = list2cmdline(cmdargs) if isinstance(cmdargs, (list, tuple)) else cmdargs  # yapf: disable
        if stream:
            return self._request("get",
                                 "/shell/stream",
                                 params={"command": cmdline},
                                 timeout=None,
                                 stream=True)
        ret = self._request("post",
                            '/shell',
                            data={
                                'command': cmdline,
                                'timeout': str(timeout)
                            },
                            timeout=timeout + 10)
        if ret.status_code != 200:
            raise RuntimeError(
                "device agent responds with an error code %d" %
                ret.status_code, ret.text)
        resp = ret.json()
        exit_code = 1 if resp.get('error') else 0
        exit_code = resp.get('exitCode', exit_code)
        shell_response = namedtuple("ShellResponse", ("output", "exit_code"))
        return shell_response(resp.get('output'), exit_code)

    def adb_shell(self, *args):
        """
        Example:
            adb_shell('pwd')
            adb_shell('ls', '-l')
            adb_shell('ls -l')

        Returns:
            string for stdout merged with stderr, after the entire shell command is completed.
        """
        # print(
        #     "DeprecatedWarning: adb_shell is deprecated, use: output, exit_code = shell(['ls', '-l']) instead"
        # )
        cmdline = args[0] if len(args) == 1 else list2cmdline(args)
        return self.shell(cmdline)[0]

    def app_start(self,
                  package_name,
                  activity=None,
                  extras={},
                  wait=False,
                  stop=False,
                  unlock=False,
                  launch_timeout=None,
                  use_monkey=False):
        """ Launch application
        Args:
            package_name (str): package name
            activity (str): app activity
            stop (bool): Stop app before starting the activity. (require activity)
            use_monkey (bool): use monkey command to start app when activity is not given
            wait (bool): wait until app started. default False

        Raises:
            SessionBrokenError
        """
        if unlock:
            self.unlock()

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
            'android.intent.category.LAUNCHER'
        ]
        args += ['-n', '{}/{}'.format(package_name, activity)]
        # -e --ez
        extra_args = []
        for k, v in extras.items():
            if isinstance(v, bool):
                extra_args.extend(['--ez', k, 'true' if v else 'false'])
            elif isinstance(v, int):
                extra_args.extend(['--ei', k, str(v)])
            else:
                extra_args.extend(['-e', k, v])
        args += extra_args
        self.shell(args)

        if wait:
            self.app_wait(package_name)

    @deprecated(version="2.0.0", reason="You should use app_current instead")
    def current_app(self):
        return self.app_current()

    @retry(EnvironmentError, delay=.5, tries=3, jitter=.1)
    def app_current(self):
        """
        Returns:
            dict(package, activity, pid?)

        Raises:
            EnvironementError

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
        raise EnvironmentError("Couldn't get focused app")

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

    def app_wait(self, package_name: str, timeout: float = 20.0,
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

    def _iter_process(self):
        """
        List processes by cmd:ps

        Returns:
            list of Process(pid, name)
        """
        headers, pids = [], {}
        Header = None
        Process = namedtuple("Process", ["user", "pid", "name"])
        for line in self.shell("ps; ps -A").output.splitlines():
            # USER PID ..... NAME
            fields = line.strip().split()
            if fields[0] == "USER":
                continue
            if not fields[1].isdigit():
                continue
            user, pid, name = fields[0], int(fields[1]), fields[-1]
            if pid in pids:
                continue
            pids[pid] = True
            yield Process(user, pid, name)

    def app_stop(self, pkg_name):
        """ Stop one application: am force-stop"""
        self.shell(['am', 'force-stop', pkg_name])

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

    def app_clear(self, pkg_name):
        """ Stop and clear app data: pm clear """
        self.shell(['pm', 'clear', pkg_name])

    def app_uninstall(self, pkg_name) -> bool:
        """ Uninstall an app 

        Returns:
            bool: success
        """
        ret = self.shell(["pm", "uninstall", pkg_name])
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

    def unlock(self):
        """ unlock screen """
        if not self.info['screenOn']:
            self.press("power")
            self.swipe(0.1, 0.9, 0.9, 0.1)

        # self.open_identify()
        # self._default_session.press("home")

    def open_identify(self, theme='black'):
        """
        Args:
            theme (str): black or red
        """
        self.shell([
            'am', 'start', '-W', '-n',
            'com.github.uiautomator/.IdentifyActivity', '-e', 'theme', theme
        ])

    def _pidof_app(self, pkg_name):
        """
        Return pid of package name
        """
        text = self._request("get", '/pidof/' + pkg_name).text
        if text.isdigit():
            return int(text)

    def push_url(self, url, dst, mode=0o644):
        """
        Args:
            url (str): http url address
            dst (str): destination
            mode (str): file mode

        Raises:
            FileNotFoundError(py3) OSError(py2)
        """
        modestr = oct(mode).replace('o', '')
        r = self._request("post",
                          '/download',
                          data={
                              'url': url,
                              'filepath': dst,
                              'mode': modestr
                          })
        if r.status_code != 200:
            raise IOError("push-url", "%s -> %s" % (url, dst), r.text)
        key = r.text.strip()
        while 1:
            r = self._request("get", '/download/' + key)
            jdata = r.json()
            message = jdata.get('message')
            if message == 'downloaded':
                log_print("downloaded")
                break
            elif message == 'downloading':
                progress = jdata.get('progress')
                if progress:
                    copied_size = progress.get('copiedSize')
                    total_size = progress.get('totalSize')
                    log_print("{} {} / {}".format(
                        message, humanize.naturalsize(copied_size),
                        humanize.naturalsize(total_size)))
                else:
                    log_print("downloading")
            else:
                log_print("unknown json:" + str(jdata))
                raise IOError(message)
            time.sleep(1)

    def push(self, src, dst, mode=0o644):
        """
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
        if isinstance(src, six.string_types):
            src = open(src, 'rb')
        r = self._request("post",
                          pathname,
                          data={'mode': modestr},
                          files={'file': src})
        if r.status_code == 200:
            return r.json()
        raise IOError("push", "%s -> %s" % (src, dst), r.text)

    def pull(self, src: str, dst: str):
        """
        Pull file from device to local

        Raises:
            FileNotFoundError(py3) OSError(py2)

        Require atx-agent >= 0.0.9
        """
        pathname = "/raw/" + src.lstrip("/")
        r = self._request("get", pathname, stream=True)
        if r.status_code != 200:
            raise FileNotFoundError("pull", src, r.text)
        with open(dst, 'wb') as f:
            shutil.copyfileobj(r.raw, f)
            if os.name == 'nt':  # hotfix windows file size zero bug
                f.close()

    def pull_content(self, src: str) -> bytes:
        """
        Read remote file content

        Raises:
            FileNotFoundError
        """
        pathname = "/raw/" + src.lstrip("/")
        r = self._request("get", pathname)
        if r.status_code != 200:
            raise FileNotFoundError("pull", src, r.text)
        return r.content

    @property
    def screenshot_uri(self):
        return 'http://%s:%d/screenshot/0' % (self._host, self._port)

    def screenshot(self, *args, **kwargs):
        """
        Take screenshot of device

        Returns:
            PIL.Image
        """
        return self.session().screenshot(*args, **kwargs)

    @property
    def device_info(self):
        if self.__devinfo:
            return self.__devinfo
        self.__devinfo = self._request("get", '/info').json()
        return self.__devinfo

    def app_info(self, pkg_name):
        """
        Get app info

        Args:
            pkg_name (str): package name

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
        resp = self._request("get", f"/packages/{pkg_name}/info")
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
        from PIL import Image
        url = f'/packages/{package_name}/icon'
        resp = self._request("get", url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))

    @property
    def wlan_ip(self):
        return self._request("get", "/wlan/ip").text.strip()

    def disable_popups(self, enable=True):
        """
        Automatic click all popups
        TODO: need fix
        """
        raise NotImplementedError()
        # self.watcher

        if enable:
            self.jsonrpc.setAccessibilityPatterns({
                "com.android.packageinstaller":
                [u"确定", u"安装", u"下一步", u"好", u"允许", u"我知道"],
                "com.miui.securitycenter": [u"继续安装"],  # xiaomi
                "com.lbe.security.miui": [u"允许"],  # xiaomi
                "android": [u"好", u"安装"],  # vivo
                "com.huawei.systemmanager": [u"立即删除"],  # huawei
                "com.android.systemui": [u"同意"],  # 锤子
            })
        else:
            self.jsonrpc.setAccessibilityPatterns({})

    def session(self,
                pkg_name=None,
                attach=False,
                launch_timeout=None,
                strict=False):
        """
        Create a new session

        Args:
            pkg_name (str): android package name
            attach (bool): attach to already running app
            launch_timeout (int): launch timeout
            strict (bool): used along with attach, 
                when attach and strict both true, SessionBrokenError will raise if app not running

        Raises:
            requests.HTTPError, SessionBrokenError
        """
        if pkg_name is None:
            return self._default_session

        if not attach:
            request_data = {"flags": "-S"}
            if launch_timeout:
                request_data["timeout"] = str(launch_timeout)
            resp = self._request("post",
                                 "/session/" + pkg_name,
                                 data=request_data)
            if resp.status_code == 410:  # Gone
                raise SessionBrokenError(pkg_name, resp.text)
            resp.raise_for_status()
            jsondata = resp.json()
            if not jsondata["success"]:
                raise SessionBrokenError("app launch failed",
                                         jsondata["error"], jsondata["output"])

            time.sleep(2.5)  # wait launch finished, maybe no need
        pid = self._pidof_app(pkg_name)
        if not pid:
            if strict:
                raise SessionBrokenError(pkg_name)
            return self.session(pkg_name,
                                attach=False,
                                launch_timeout=launch_timeout)

        return Session(self, pkg_name, pid)

    @property
    @cache_return
    def xpath(self) -> xpath.XPath:
        return xpath.XPath(self)

    @property
    @cache_return
    def settings(self) -> Settings:
        return Settings(self)

    @property
    @cache_return
    def watcher(self) -> Watcher:
        return Watcher(self)

    @property
    @cache_return
    def taobao(self):
        try:
            import uiautomator2_taobao as tb
        except ImportError:
            raise RuntimeError(
                "This method can only use inside alibaba network")
        return tb.Taobao(self)

    @property
    @cache_return
    def alibaba(self):
        try:
            import uiautomator2_taobao as tb
        except ImportError:
            raise RuntimeError(
                "This method can only use inside alibaba network")
        return tb.Alibaba(self)

    @property
    @cache_return
    def image(self):
        from uiautomator2 import image as _image
        return _image.ImageX(self)
    
    #@property
    #@cache_return
    #def screenrecord(self):
        #from uiautomator2 import screenrecord as _sr
        #return _sr.Screenrecord(self)

    def __getattr__(self, attr):
        if attr in self._cached_plugins:
            return self._cached_plugins[attr]
        if attr.startswith('ext_'):
            plugin_name = attr[4:]
            if plugin_name not in self.__plugins:
                if plugin_name == 'xpath':
                    import uiautomator2.xpath as xpath
                    xpath.init()
                else:
                    raise ValueError("plugin \"%s\" not registed" %
                                     plugin_name)
            func, args, kwargs = self.__plugins[plugin_name]
            obj = functools.partial(func, self)(*args, **kwargs)
            self._cached_plugins[attr] = obj
            return obj
        try:
            return getattr(self._default_session, attr)
        except AttributeError:
            raise AttributeError(
                "'Session or Device' object has no attribute '%s'" % attr)

    def __call__(self, **kwargs) -> Session:
        return self._default_session(**kwargs)


class AdbShell(object):
    def __init__(self, shellfn):
        """
        Args:
            shellfn: Shell function
        """
        self.shell = shellfn

    def wmsize(self):
        """ get window size
        Returns:
            (width, height)
        """
        output, _ = self.shell("wm size")
        m = re.match(r"Physical size: (\d+)x(\d+)", output)
        if m:
            return map(int, m.groups())
        raise RuntimeError("Can't parse wm size: " + output)

    def is_screen_on(self):
        output, _ = self.shell("dumpsys power")
        return 'mHoldingDisplaySuspendBlocker=true' in output

    def keyevent(self, v):
        """
        Args:
            v: eg home wakeup back
        """
        v = v.upper()
        self.shell("input keyevent " + v)

    def _adjust_pos(self, x, y, w=None, h=None):
        if x < 1:
            x = x * w
        if y < 1:
            y = y * h
        return (x, y)

    def swipe(self, x0, y0, x1, y1):
        w, h = None, None
        if x0 < 1 or y0 < 1 or x1 < 1 or y1 < 1:
            w, h = self.wmsize()
        x0, y0 = self._adjust_pos(x0, y0, w, h)
        x1, y1 = self._adjust_pos(x1, y1, w, h)
        self.shell("input swipe %d %d %d %d" % (x0, y0, x1, y1))


UIAutomatorServer = Device  # Deprecated UIAutomatorServer
