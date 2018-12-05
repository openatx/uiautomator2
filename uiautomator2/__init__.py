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
import hashlib
import time
import functools
import json
import io
import os
import re
import sys
import shutil
import xml.dom.minidom
import threading
import warnings
import logging
import functools
from datetime import datetime
from subprocess import list2cmdline
from collections import namedtuple

import six
import humanize
import progress.bar
from retry import retry
import six.moves.urllib.parse as urlparse

if six.PY2:
    FileNotFoundError = OSError

import requests
from uiautomator2 import adbutils
from uiautomator2.version import __apk_version__, __atx_agent_version__
from uiautomator2 import simplexml

DEBUG = False
HTTP_TIMEOUT = 60

_INPUT_METHOD_RE = re.compile(r'mCurMethodId=([-_./\w]+)')


class UiaError(Exception):
    pass


class GatewayError(UiaError):
    def __init__(self, response, description):
        self.response = response
        self.description = description

    def __str__(self):
        return "uiautomator2.GatewayError(" + self.description + ")"


class JsonRpcError(UiaError):
    @staticmethod
    def format_errcode(errcode):
        m = {
            -32700: 'Parse error',
            -32600: 'Invalid Request',
            -32601: 'Method not found',
            -32602: 'Invalid params',
            -32603: 'Internal error',
            -32001: 'Jsonrpc error',
            -32002: 'Client error',
        }
        if errcode in m:
            return m[errcode]
        if errcode >= -32099 and errcode <= -32000:
            return 'Server error'
        return 'Unknown error'

    def __init__(self, error={}, method=None):
        self.code = error.get('code')
        self.message = error.get('message', '')
        self.data = error.get('data', '')
        self.method = method

    def __str__(self):
        return '%d %s: <%s> data: %s, method: %s' % (
            self.code, self.format_errcode(self.code), self.message, self.data,
            self.method)

    def __repr__(self):
        return repr(str(self))


class SessionBrokenError(UiaError):
    pass


class UiObjectNotFoundError(JsonRpcError):
    pass


class UiAutomationNotConnectedError(JsonRpcError):
    pass


class NullObjectExceptionError(JsonRpcError):
    pass


class NullPointerExceptionError(JsonRpcError):
    pass


class StaleObjectExceptionError(JsonRpcError):
    pass


class _ProgressBar(progress.bar.Bar):
    message = "progress"
    suffix = '%(percent)d%% [%(eta_td)s, %(speed)s]'

    @property
    def speed(self):
        return humanize.naturalsize(
            self.elapsed and self.index / self.elapsed, gnu=True) + '/s'


def log_print(s):
    thread_name = threading.current_thread().getName()
    print(thread_name + ": " + datetime.now().strftime('%H:%M:%S,%f')[:-3] +
          " " + s)


def intersect(rect1, rect2):
    top = rect1["top"] if rect1["top"] > rect2["top"] else rect2["top"]
    bottom = rect1["bottom"] if rect1["bottom"] < rect2["bottom"] else rect2[
        "bottom"]
    left = rect1["left"] if rect1["left"] > rect2["left"] else rect2["left"]
    right = rect1["right"] if rect1["right"] < rect2["right"] else rect2[
        "right"]
    return left, top, right, bottom


def U(x):
    if six.PY3:
        return x
    return x.decode('utf-8') if type(x) is str else x


def E(x):
    if six.PY3:
        return x
    return x.encode('utf-8') if type(x) is unicode else x


def _is_wifi_addr(addr):
    if not addr:
        return False
    if re.match(r"^https?://", addr):
        return True
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", addr)
    if m and m.group(1) != "127.0.0.1":
        return True
    return False


def hooks_wrap(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        name = fn.__name__.lstrip('_')
        self.server.hooks_apply("before", name, args, kwargs, None)
        ret = fn(self, *args, **kwargs)
        self.server.hooks_apply("after", name, args, kwargs, ret)
    return inner


def connect(addr=None):
    """
    Args:
        addr (str): uiautomator server address or serial number. default from env-var ANDROID_DEVICE_IP

    Returns:
        UIAutomatorServer

    Example:
        connect("10.0.0.1:7912")
        connect("10.0.0.1") # use default 7912 port
        connect("http://10.0.0.1")
        connect("http://10.0.0.1:7912")
        connect("cff1123ea")  # adb device serial number
    """
    if not addr or addr == '+':
        addr = os.getenv('ANDROID_DEVICE_IP')
    if _is_wifi_addr(addr):
        return connect_wifi(addr)
    return connect_usb(addr)


def connect_wifi(addr=None):
    """
    Args:
        addr (str) uiautomator server address.

    Returns:
        UIAutomatorServer

    Examples:
        connect_wifi("10.0.0.1")
    """
    if '://' not in addr:
        addr = 'http://' + addr
    if addr.startswith('http://'):
        u = urlparse.urlparse(addr)
        host = u.hostname
        port = u.port or 7912
        return UIAutomatorServer(host, port)
    else:
        raise RuntimeError("address should start with http://")


def connect_usb(serial=None):
    """
    Args:
        serial (str): android device serial

    Returns:
        UIAutomatorServer
    """
    adb = adbutils.Adb(serial)
    lport = adb.forward_port(7912)
    d = connect_wifi('127.0.0.1:' + str(lport))
    if not d.agent_alive:
        warnings.warn("backend atx-agent is not alive, start again ...",
                      RuntimeWarning)
        adb.execute(
            "shell", "PATH=$PATH:/data/local/tmp:/data/data/com.android/shell",
            "atx-agent", "server", "-d")
        deadline = time.time() + 3
        while time.time() < deadline:
            if d.alive:
                break
    elif not d.alive:
        warnings.warn("backend uiautomator2 is not alive, start again ...",
                      RuntimeWarning)
        d.reset_uiautomator()
    return d


class TimeoutRequestsSession(requests.Session):
    def __init__(self):
        super(TimeoutRequestsSession, self).__init__()
        # refs: https://stackoverflow.com/questions/33895739/python-requests-cant-load-any-url-remote-end-closed-connection-without-respo
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = HTTP_TIMEOUT
        verbose = hasattr(self, 'debug') and self.debug
        if verbose:
            data = kwargs.get('data') or ''
            if isinstance(data, dict):
                data = 'dict:' + json.dumps(data)
            time_start = time.time()
            print(datetime.now().strftime("%H:%M:%S.%f")[:-3],
                  "$ curl -X {method} -d '{data}' '{url}'".format(
                      method=method, url=url, data=data))
        try:
            resp = super(TimeoutRequestsSession, self).request(
                method, url, **kwargs)
        except requests.ConnectionError:
            raise EnvironmentError(
                "atx-agent is not running. Fix it with following steps.\n1. Plugin device into computer.\n2. Run command \"python -m uiautomator2 init\""
            )
        else:
            if verbose:
                print(datetime.now().strftime("%H:%M:%S.%f")[:-3],
                      "Response (%d ms) >>>\n" %
                      ((time.time() - time_start) * 1000) +
                      resp.text.rstrip() + "\n<<< END")
            return resp


def plugin_register(name, plugin, *args, **kwargs):
    """
    Add plugin into UIAutomatorServer
    
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
    UIAutomatorServer.plugins()[name] = (plugin, args, kwargs)


def plugin_clear():
    UIAutomatorServer.plugins().clear()


class UIAutomatorServer(object):
    __isfrozen = False
    __plugins = {}

    def __init__(self, host, port=7912):
        """
        Args:
            host (str): host address
            port (int): port number

        Raises:
            EnvironmentError
        """
        self._host = host
        self._port = port
        self._reqsess = TimeoutRequestsSession(
        )  # use requests.Session to enable HTTP Keep-Alive
        self._server_url = 'http://{}:{}'.format(host, port)
        self._server_jsonrpc_url = self._server_url + "/jsonrpc/0"
        self._default_session = Session(self, None)
        self._cached_plugins = {}
        self.__devinfo = None
        self._hooks = {}
        self.platform = None  # hot fix for weditor

        self.ash = AdbShell(self.shell)  # the powerful adb shell
        self.wait_timeout = 20.0  # wait element timeout
        self.click_post_delay = None  # wait after each click
        self._freeze()  # prevent creating new attrs
        # self._atx_agent_check()

    def _freeze(self):
        self.__isfrozen = True

    @staticmethod
    def plugins():
        return UIAutomatorServer.__plugins

    def __setattr__(self, key, value):
        """ Prevent creating new attributes outside __init__ """
        if self.__isfrozen and not hasattr(self, key):
            raise TypeError("Key %s does not exist in class %r" % (key, self))
        object.__setattr__(self, key, value)

    def __str__(self):
        return 'uiautomator2 object for %s:%d' % (self._host, self._port)

    def __repr__(self):
        return str(self)

    def _atx_agent_check(self):
        """ check atx-agent health status and version """
        try:
            version = self._reqsess.get(
                self.path2url('/version'), timeout=5).text
            if version != __atx_agent_version__:
                warnings.warn(
                    'Version dismatch, expect "%s" actually "%s"' %
                    (__atx_agent_version__, version),
                    Warning,
                    stacklevel=2)
            # Cancel bellow code to make connect() return faster.
            # launch service to prevent uiautomator killed by Android system
            # self.adb_shell('am', 'startservice', '-n', 'com.github.uiautomator/.Service')
        except (requests.ConnectionError, ) as e:
            raise EnvironmentError(
                "atx-agent is not responding, need to init device first")

    @property
    def debug(self):
        return hasattr(self._reqsess, 'debug') and self._reqsess.debug

    @debug.setter
    def debug(self, value):
        self._reqsess.debug = bool(value)

    @property
    def serial(self):
        return self.shell(['getprop', 'ro.serialno'])[0].strip()

    @property
    def jsonrpc(self):
        """
        Make jsonrpc call easier
        For example:
            self.jsonrpc.pressKey("home")
        """
        return self.setup_jsonrpc()

    def path2url(self, path):
        return urlparse.urljoin(self._server_url, path)

    def window_size(self):
        """ return (width, height) """
        info = self._reqsess.get(self.path2url('/info')).json()
        w, h = info['display']['width'], info['display']['height']
        if (w > h) != (self.info["displayRotation"] % 2 == 1):
            w, h = h, w
        return w, h

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
        if not jsonrpc_url:
            jsonrpc_url = self._server_jsonrpc_url

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
                return self.server.jsonrpc_retry_call(jsonrpc_url, self.method,
                                                      params, http_timeout)

        return JSONRpcWrapper(self)

    def jsonrpc_retry_call(self, *args,
                           **kwargs):  # method, params=[], http_timeout=60):
        try:
            return self.jsonrpc_call(*args, **kwargs)
        except (GatewayError, ):
            warnings.warn(
                "uiautomator2 is not reponding, restart uiautomator2 automatically",
                RuntimeWarning,
                stacklevel=1)
            # for XiaoMi, want to recover uiautomator2 must start app:com.github.uiautomator
            self.reset_uiautomator()
            return self.jsonrpc_call(*args, **kwargs)
        except UiAutomationNotConnectedError:
            warnings.warn(
                "UiAutomation not connected, restart uiautoamtor",
                RuntimeWarning,
                stacklevel=1)
            self.reset_uiautomator()
            return self.jsonrpc_call(*args, **kwargs)
        except (NullObjectExceptionError,
                NullPointerExceptionError, StaleObjectExceptionError) as e:
            if args[1] != 'dumpWindowHierarchy': # args[1] method
                warnings.warn(
                    "uiautomator2 raise exception %s, and run code again" % e,
                    RuntimeWarning,
                    stacklevel=1)
            time.sleep(1)
            return self.jsonrpc_call(*args, **kwargs)

    def jsonrpc_call(self, jsonrpc_url, method, params=[], http_timeout=60):
        """ jsonrpc2 call
        Refs:
            - http://www.jsonrpc.org/specification
        """
        request_start = time.time()
        data = {
            "jsonrpc": "2.0",
            "id": self._jsonrpc_id(method),
            "method": method,
            "params": params,
        }
        data = json.dumps(data).encode('utf-8')
        res = self._reqsess.post(
            jsonrpc_url, # +"?m="+method, #?method is for debug
            headers={"Content-Type": "application/json"},
            timeout=http_timeout,
            data=data)
        if DEBUG:
            print("Shell$ curl -X POST -d '{}' {}".format(data, jsonrpc_url))
            print("Output> " + res.text)
        if res.status_code == 502:
            raise GatewayError(res, "gateway error, time used %.1fs" %
                               (time.time() - request_start))
        if res.status_code == 410:  # http status gone: session broken
            raise SessionBrokenError("app quit or crash", jsonrpc_url,
                                     res.text)
        if res.status_code != 200:
            raise UiaError(jsonrpc_url, data, res.status_code, res.text,
                           "HTTP Return code is not 200", res.text)
        jsondata = res.json()
        error = jsondata.get('error')
        if not error:
            return jsondata.get('result')

        # error happends
        err = JsonRpcError(error, method)

        if isinstance(err.data, six.string_types) and 'UiAutomation not connected' in err.data:
            err.__class__ = UiAutomationNotConnectedError
        elif err.message:
            if 'uiautomator.UiObjectNotFoundException' in err.message:
                err.__class__ = UiObjectNotFoundError
            elif 'android.support.test.uiautomator.StaleObjectException' in err.message:
                # StaleObjectException
                # https://developer.android.com/reference/android/support/test/uiautomator/StaleObjectException.html
                # A StaleObjectException exception is thrown when a UiObject2 is used after the underlying View has been destroyed.
                # In this case, it is necessary to call findObject(BySelector) to obtain a new UiObject2 instance.
                err.__class__ = StaleObjectExceptionError
            elif 'java.lang.NullObjectException' in err.message:
                err.__class__ = NullObjectExceptionError
            elif 'java.lang.NullPointerException' == err.message:
                err.__class__ = NullPointerExceptionError
        raise err

    def _jsonrpc_id(self, method):
        m = hashlib.md5()
        m.update(("%s at %f" % (method, time.time())).encode("utf-8"))
        return m.hexdigest()

    @property
    def agent_alive(self):
        try:
            r = self._reqsess.get(self.path2url('/version'), timeout=2)
            return r.status_code == 200
        except:
            return False

    @property
    def alive(self):
        try:
            r = self._reqsess.get(self.path2url('/ping'), timeout=2)
            if r.status_code != 200:
                return False
            r = self._reqsess.post(
                self.path2url('/jsonrpc/0'),
                data=json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "deviceInfo"
                }),
                timeout=2)
            if r.status_code != 200:
                return False
            if r.json().get('error'):
                return False
            return True
        except requests.exceptions.ReadTimeout:
            return False
        except EnvironmentError:
            return False

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

            def start(self):
                res = u2obj._reqsess.post(u2obj.path2url('/uiautomator'))
                res.raise_for_status()

            def stop(self):
                res = u2obj._reqsess.delete(u2obj.path2url('/uiautomator'))
                if res.status_code != 200:
                    warnings.warn(res.text)

        return _Service(name)

    def reset_uiautomator(self):
        """
        Reset uiautomator

        Raises:
            RuntimeError
        """
        # self.open_identify()
        self._reqsess.delete(
            self.path2url('/uiautomator'))  # stop uiautomator keeper first
        # wait = not unlock  # should not wait IdentifyActivity open or it will stuck sometimes
        self.app_start(  # may also stuck here.
            'com.github.uiautomator',
            '.MainActivity',
            wait=False,
            stop=True)
        time.sleep(.5)

        # launch atx-agent uiautomator keeper
        self._reqsess.post(self.path2url('/uiautomator'))

        # wait until uiautomator2 service working
        deadline = time.time() + 20.0
        while time.time() < deadline:
            print(
                time.strftime("[%Y-%m-%d %H:%M:%S]"),
                "uiautomator is starting ...")
            if self.alive:
                # keyevent BACK if current is com.github.uiautomator
                # XiaoMi uiautomator will kill the app(com.github.uiautomator) when launch
                #   it is better to start a service to make uiautomator live longer
                if self.current_app()['package'] != 'com.github.uiautomator':
                    self.shell([
                        'am', 'startservice', '-n',
                        'com.github.uiautomator/.Service'
                    ])
                    time.sleep(1.5)
                else:
                    time.sleep(.5)
                    self.shell(['input', 'keyevent', 'BACK'])
                print("uiautomator back to normal")
                return True
            time.sleep(1)
        raise RuntimeError(
            "Uiautomator started failed. Find solutions in https://github.com/openatx/uiautomator2/wiki/Common-issues"
        )

    def healthcheck(self):
        """
        Reset device into ready state

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
        self.reset_uiautomator()

    def app_install(self, url, installing_callback=None, server=None):
        """
        {u'message': u'downloading', "progress": {u'totalSize': 407992690, u'copiedSize': 49152}}

        Returns:
            packageName

        Raises:
            RuntimeError
        """
        r = self._reqsess.post(self.path2url('/install'), data={'url': url})
        if r.status_code != 200:
            raise RuntimeError("app install error:", r.text)
        id = r.text.strip()
        print(time.strftime('%H:%M:%S'), "id:", id)
        return self._wait_install_finished(id, installing_callback)

    def _wait_install_finished(self, id, installing_callback):
        bar = None
        downloaded = True

        while True:
            resp = self._reqsess.get(self.path2url('/install/' + id))
            resp.raise_for_status()
            jdata = resp.json()
            message = jdata['message']
            pg = jdata.get('progress')

            def notty_print_progress(pg):
                written = pg['copiedSize']
                total = pg['totalSize']
                print(
                    time.strftime('%H:%M:%S'), 'downloading %.1f%% [%s/%s]' %
                    (100.0 * written / total,
                     humanize.naturalsize(written, gnu=True),
                     humanize.naturalsize(total, gnu=True)))

            if message == 'downloading':
                downloaded = False
                if pg:  # if there is a progress
                    if hasattr(sys.stdout, 'isatty'):
                        if sys.stdout.isatty():
                            if not bar:
                                bar = _ProgressBar(
                                    time.strftime('%H:%M:%S') + ' downloading',
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
                self._reqsess.delete(self.path2url('/install/' + id))
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
        if isinstance(cmdargs, (list, tuple)):
            cmdargs = list2cmdline(cmdargs)
        if stream:
            return self._reqsess.get(
                self.path2url("/shell/stream"),
                params={"command": cmdargs},
                stream=True)
        ret = self._reqsess.post(
            self.path2url('/shell'),
            data={
                'command': cmdargs,
                'timeout': str(timeout)
            })
        if ret.status_code != 200:
            raise RuntimeError("device agent responds with an error code %d" %
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
                  pkg_name,
                  activity=None,
                  extras={},
                  wait=True,
                  stop=False,
                  unlock=False):
        """ Launch application
        Args:
            pkg_name (str): package name
            activity (str): app activity
            stop (bool): Stop app before starting the activity. (require activity)
        """
        if unlock:
            self.unlock()

        if activity:
            # -D: enable debugging
            # -W: wait for launch to complete
            # -S: force stop the target app before starting the activity
            # --user <USER_ID> | current: Specify which user to run as; if not
            #    specified then run as the current user.
            # -e <EXTRA_KEY> <EXTRA_STRING_VALUE>
            # --ei <EXTRA_KEY> <EXTRA_INT_VALUE>
            # --ez <EXTRA_KEY> <EXTRA_BOOLEAN_VALUE>
            args = ['am', 'start', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER']
            if wait:
                args.append('-W')
            if stop:
                args.append('-S')
            args += ['-n', '{}/{}'.format(pkg_name, activity)]
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
            # 'am', 'start', '-W', '-n', '{}/{}'.format(pkg_name, activity))
            self.shell(args)
        else:
            if stop:
                self.app_stop(pkg_name)
            self.shell([
                'monkey', '-p', pkg_name, '-c',
                'android.intent.category.LAUNCHER', '1'
            ])

    @retry(EnvironmentError, delay=.5, tries=3, jitter=.1)
    def current_app(self):
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
            r'mCurrentFocus=Window{.*\s+(?P<package>[^\s]+)/(?P<activity>[^\s]+)\}')
        m = _focusedRE.search(self.shell(['dumpsys', 'window', 'windows'])[0])
        if m:
            return dict(
                package=m.group('package'), activity=m.group('activity'))

        # try: adb shell dumpsys activity top
        _activityRE = re.compile(
            r'ACTIVITY (?P<package>[^\s]+)/(?P<activity>[^/\s]+) \w+ pid=(?P<pid>\d+)'
        )
        output, _ = self.shell(['dumpsys', 'activity', 'top'])
        ms = _activityRE.finditer(output)
        ret = None
        for m in ms:
            ret = dict(
                package=m.group('package'),
                activity=m.group('activity'),
                pid=int(m.group('pid')))
        if ret: # get last result
            return ret
        raise EnvironmentError("Couldn't get focused app")

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
        output, _ = self.shell(['pm', 'list', 'packages', '-3'])
        pkgs = re.findall('package:([^\s]+)', output)
        process_names = re.findall('([^\s]+)$', self.shell('ps')[0], re.M)
        kill_pkgs = set(pkgs).intersection(process_names).difference(
            our_apps + excludes)
        kill_pkgs = list(kill_pkgs)
        for pkg_name in kill_pkgs:
            self.app_stop(pkg_name)
        return kill_pkgs

    def app_clear(self, pkg_name):
        """ Stop and clear app data: pm clear """
        self.shell(['pm', 'clear', pkg_name])

    def app_uninstall(self, pkg_name):
        """ Uninstall an app """
        self.shell(["pm", "uninstall", pkg_name])

    def app_uninstall_all(self, excludes=[], verbose=False):
        """ Uninstall all apps """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        output, _ = self.shell(['pm', 'list', 'packages', '-3'])
        pkgs = re.findall('package:([^\s]+)', output)
        pkgs = set(pkgs).difference(our_apps + excludes)
        pkgs = list(pkgs)
        for pkg_name in pkgs:
            if verbose:
                print("uninstalling", pkg_name)
            self.app_uninstall(pkg_name)
        return pkgs

    def unlock(self):
        """ unlock screen """
        self.open_identify()
        self._default_session.press("home")

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
        text = self._reqsess.get(self.path2url('/pidof/' + pkg_name)).text
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
        r = self._reqsess.post(
            self.path2url('/download'),
            data={
                'url': url,
                'filepath': dst,
                'mode': modestr
            })
        if r.status_code != 200:
            raise IOError("push-url", "%s -> %s" % (url, dst), r.text)
        key = r.text.strip()
        while 1:
            r = self._reqsess.get(self.path2url('/download/' + key))
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
        pathname = self.path2url('/upload/' + dst.lstrip('/'))
        if isinstance(src, six.string_types):
            src = open(src, 'rb')
        r = self._reqsess.post(
            pathname, data={'mode': modestr}, files={'file': src})
        if r.status_code == 200:
            return r.json()
        raise IOError("push", "%s -> %s" % (src, dst), r.text)

    def pull(self, src, dst):
        """
        Pull file from device to local

        Raises:
            FileNotFoundError(py3) OSError(py2)

        Require atx-agent >= 0.0.9
        """
        pathname = self.path2url("/raw/" + src.lstrip("/"))
        r = self._reqsess.get(pathname, stream=True)
        if r.status_code != 200:
            raise FileNotFoundError("pull", src, r.text)
        with open(dst, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

    @property
    def screenshot_uri(self):
        return 'http://%s:%d/screenshot/0' % (self._host, self._port)

    @property
    def device_info(self):
        if self.__devinfo:
            return self.__devinfo
        self.__devinfo = self._reqsess.get(self.path2url('/info')).json()
        return self.__devinfo

    @property
    def wlan_ip(self):
        return self._reqsess.get(self.path2url("/wlan/ip")).text.strip()

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

    def session(self, pkg_name=None, attach=False):
        """
        Create a new session

        Args:
            pkg_name (str): android package name
            attach (bool): attach to already running app

        Raises:
            requests.HTTPError, SessionBrokenError
        """
        if pkg_name is None:
            return self._default_session

        if not attach:
            resp = self._reqsess.post(
                self.path2url("/session/" + pkg_name), data={"flags": "-W -S"})
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
            raise SessionBrokenError(pkg_name)
        return Session(self, pkg_name, pid)

    def __getattr__(self, attr):
        if attr in self._cached_plugins:
            return self._cached_plugins[attr]
        if attr.startswith('ext_'):
            plugin_name = attr[4:]
            if plugin_name not in self.__plugins:
                if plugin_name == 'xpath':
                    import uiautomator2.ext.xpath as xpath
                    xpath.init()
                else:
                    raise ValueError("plugin \"%s\" not registed" % plugin_name)
            func, args, kwargs = self.__plugins[plugin_name]
            obj = functools.partial(func, self)(*args, **kwargs)
            self._cached_plugins[attr] = obj
            return obj
        try:
            return getattr(self._default_session, attr)
        except AttributeError:
            raise AttributeError("'Session or UIAutomatorServer' object has no attribute '%s'" % attr)

    def __call__(self, **kwargs):
        return self._default_session(**kwargs)


def check_alive(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not self.running():
            raise SessionBrokenError(self._pkg_name)
        return fn(self, *args, **kwargs)

    return inner


class Session(object):
    __orientation = (  # device orientation
        (0, "natural", "n", 0), (1, "left", "l", 90),
        (2, "upsidedown", "u", 180), (3, "right", "r", 270))

    def __init__(self, server, pkg_name=None, pid=None):
        self.server = server
        self._pkg_name = pkg_name
        self._pid = pid
        self._jsonrpc = server.jsonrpc
        if pid and pkg_name:
            jsonrpc_url = server.path2url('/session/%d:%s/jsonrpc/0' %
                                          (pid, pkg_name))
            self._jsonrpc = server.setup_jsonrpc(jsonrpc_url)

        # hot fix for session missing shell function
        self.shell = self.server.shell

    def __repr__(self):
        if self._pid and self._pkg_name:
            return "<uiautomator2.Session pid:%d pkgname:%s>" % (
                self._pid, self._pkg_name)
        return super(Session, self).__repr__()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def implicitly_wait(self, seconds=None):
        """set default wait timeout
        Args:
            seconds(float): to wait element show up
        """
        if seconds is not None:
            self.server.wait_timeout = seconds
        return self.server.wait_timeout

    def close(self):
        """ close app """
        if self._pkg_name:
            self.server.app_stop(self._pkg_name)

    def running(self):
        """
        Check is session is running. return bool
        """
        if self._pid and self._pkg_name:
            ping_url = self.server.path2url('/session/%d:%s/ping' %
                                            (self._pid, self._pkg_name))
            return self.server._reqsess.get(ping_url).text.strip() == 'pong'
        # warnings.warn("pid and pkg_name is not set, ping will always return True", Warning, stacklevel=1)
        return True

    @property
    def jsonrpc(self):
        return self._jsonrpc

    @property
    def pos_rel2abs(self):
        size = []

        def convert(x, y):
            assert x >= 0
            assert y >= 0

            if (x < 1 or y < 1) and not size:
                size.extend(
                    self.server.window_size())  # size will be [width, height]

            if x < 1:
                x = int(size[0] * x)
            if y < 1:
                y = int(size[1] * y)
            return x, y

        return convert

    def make_toast(self, text, duration=1.0):
        """ Show toast
        Args:
            text (str): text to show
            duration (float): seconds of display
        """
        warnings.warn(
            "Use d.toast.show(text, duration) instead.",
            DeprecationWarning,
            stacklevel=2)
        return self.jsonrpc.makeToast(text, duration * 1000)

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

    @check_alive
    def set_fastinput_ime(self, enable=True):
        """ Enable of Disable FastInputIME """
        fast_ime = 'com.github.uiautomator/.FastInputIME'
        if enable:
            self.server.shell(['ime', 'enable', fast_ime])
            self.server.shell(['ime', 'set', fast_ime])
        else:
            self.server.shell(['ime', 'disable', fast_ime])

    @check_alive
    def send_keys(self, text):
        """
        Raises:
            EnvironmentError
        """
        try:
            self.wait_fastinput_ime()
            btext = U(text).encode('utf-8')
            base64text = base64.b64encode(btext).decode()
            self.server.shell([
                'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'text',
                base64text
            ])
            return True
        except EnvironmentError:
            warnings.warn(
                "set FastInputIME failed. use \"d(focused=True).set_text instead\"",
                Warning)
            return self(focused=True).set_text(text)
            # warnings.warn("set FastInputIME failed. use \"adb shell input text\" instead", Warning)
            # self.server.adb_shell("input", "text", text.replace(" ", "%s"))

    @check_alive
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
        self.server.shell(['am', 'broadcast', '-a', 'ADB_EDITOR_CODE', '--ei', 'code', str(code)])

    @check_alive
    def clear_text(self):
        """ clear text
        Raises:
            EnvironmentError
        """
        try:
            self.wait_fastinput_ime()
            self.server.shell(['am', 'broadcast', '-a', 'ADB_CLEAR_TEXT'])
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
        if not self.server.serial:  # maybe simulator eg: genymotion, 海马玩模拟器
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
        dim, _ = self.server.shell(['dumpsys', 'input_method'])
        m = _INPUT_METHOD_RE.search(dim)
        method_id = None if not m else m.group(1)
        shown = "mInputShown=true" in dim
        return (method_id, shown)

    def tap(self, x, y):
        """
        alias of click
        """
        self.click(x, y)

    @property
    def touch(self):
        """
        ACTION_DOWN: 0 ACTION_MOVE: 2
        touch.down(x, y)
        touch.move(x, y)
        touch.up()
        """
        ACTION_DOWN = 0
        ACTION_MOVE = 2
        ACTION_UP = 1

        obj = self

        class _Touch(object):
            def down(self, x, y):
                obj.jsonrpc.injectInputEvent(ACTION_DOWN, x, y, 0)

            def move(self, x, y):
                obj.jsonrpc.injectInputEvent(ACTION_MOVE, x, y, 0)

            def up(self, x, y):
                obj.jsonrpc.injectInputEvent(ACTION_UP, x, y, 0)

        return _Touch()

    def click(self, x, y):
        """
        click position
        """
        x, y = self.pos_rel2abs(x, y)
        self._click(x, y)
    
    @hooks_wrap
    def _click(self, x, y):
        self.jsonrpc.click(x, y)
        if self.server.click_post_delay:  # click code delay
            time.sleep(self.server.click_post_delay)

    def double_click(self, x, y, duration=0.1):
        """
        double click position
        """
        x, y = self.pos_rel2abs(x, y)
        self.touch.down(x, y)
        self.touch.up(x, y)
        time.sleep(duration)
        self.click(x, y)  # use click last is for htmlreport

    def long_click(self, x, y, duration=None):
        '''long click at arbitrary coordinates.
        Args:
            duration (float): seconds of pressed
        '''
        if not duration:
            duration = 0.5
        x, y = self.pos_rel2abs(x, y)
        return self._long_click(x, y, duration)
    
    @hooks_wrap
    def _long_click(self, x, y, duration):
        self.touch.down(x, y)
        time.sleep(duration)
        self.touch.up(x, y)
        return self

    def swipe(self, fx, fy, tx, ty, duration=0.1, steps=None):
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
        if not steps:
            steps = int(duration * 200)
        self._swipe(fx, fy, tx, ty, steps)
    
    @hooks_wrap
    def _swipe(self, fx, fy, tx, ty, steps):
        return self.jsonrpc.swipe(fx, fy, tx, ty, steps)

    def swipe_points(self, points, duration=0.5):
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
        return self.jsonrpc.swipePoints(ppoints, int(duration * 200))

    def drag(self, sx, sy, ex, ey, duration=0.5):
        '''Swipe from one point to another point.'''
        rel2abs = self.pos_rel2abs
        sx, sy = rel2abs(sx, sy)
        ex, ey = rel2abs(ex, ey)
        return self.jsonrpc.drag(sx, sy, ex, ey, int(duration * 200))

    @retry(
        (IOError, SyntaxError), delay=.5, tries=5, jitter=0.1,
        max_delay=1)  # delay .5, .6, .7, .8 ...
    def screenshot(self, filename=None, format='pillow'):
        """
        Image format is JPEG

        Args:
            filename (str): saved filename
            format (string): used when filename is empty. one of "pillow" or "opencv"

        Raises:
            IOError, SyntaxError

        Examples:
            screenshot("saved.jpg")
            screenshot().save("saved.png")
            cv2.imwrite('saved.jpg', screenshot(format='opencv'))
        """
        r = requests.get(self.server.screenshot_uri, timeout=10)
        if filename:
            with open(filename, 'wb') as f:
                f.write(r.content)
            return filename
        elif format == 'pillow':
            from PIL import Image
            buff = io.BytesIO(r.content)
            return Image.open(buff)
        elif format == 'opencv':
            import cv2
            import numpy as np
            nparr = np.fromstring(r.content, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif format == 'raw':
            return r.content
        else:
            raise RuntimeError("Invalid format " + format)

    @retry(NullPointerExceptionError, delay=.5, tries=5, jitter=0.2)
    def dump_hierarchy(self, compressed=False, pretty=False):
        content = self.jsonrpc.dumpWindowHierarchy(compressed, None)
        if pretty and "\n " not in content:
            xml_text = xml.dom.minidom.parseString(content.encode("utf-8"))
            content = U(xml_text.toprettyxml(indent='  '))
        return content

    def freeze_rotation(self, freeze=True):
        '''freeze or unfreeze the device rotation in current status.'''
        self.jsonrpc.freezeRotation(freeze)

    def press(self, key, meta=None):
        """
        press key via name or key code. Supported key name includes:
            home, back, left, right, up, down, center, menu, search, enter,
            delete(or del), recent(recent apps), volume_up, volume_down,
            volume_mute, camera, power.
        """
        if isinstance(key, int):
            return self.jsonrpc.pressKeyCode(
                key, meta) if meta else self.server.jsonrpc.pressKeyCode(key)
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

    def exists(self, **kwargs):
        return self(**kwargs).exists

    def xpath(self, xpath, source=None):
        """
        Args:
            xpath: expression of XPath2.0
            source: optional, hierarchy from dump_hierarchy()

        Returns:
            XPathSelector
        """
        return XPathSelector(xpath, self.server, source)

    def watcher(self, name):
        obj = self

        class Watcher(object):
            def __init__(self):
                self.__selectors = []

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasWatcherTriggered(name)

            def remove(self):
                obj.server.jsonrpc.removeWatcher(name)

            def when(self, **kwargs):
                self.__selectors.append(Selector(**kwargs))
                return self

            def click(self, **kwargs):
                target = Selector(**kwargs) if kwargs else self.__selectors[-1]
                obj.server.jsonrpc.registerClickUiObjectWatcher(
                    name, self.__selectors, target)

            def press(self, *keys):
                """
                key (str): on of
                    ("home", "back", "left", "right", "up", "down", "center",
                    "search", "enter", "delete", "del", "recent", "volume_up",
                    "menu", "volume_down", "volume_mute", "camera", "power")
                """
                obj.server.jsonrpc.registerPressKeyskWatcher(
                    name, self.__selectors, keys)

        return Watcher()

    @property
    def watchers(self):
        obj = self

        class Watchers(list):
            def __init__(self):
                for watcher in obj.server.jsonrpc.getWatchers():
                    self.append(watcher)

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasAnyWatcherTriggered()

            def remove(self, name=None):
                if name:
                    obj.server.jsonrpc.removeWatcher(name)
                else:
                    for name in self:
                        obj.server.jsonrpc.removeWatcher(name)

            def reset(self):
                obj.server.jsonrpc.resetWatcherTriggers()
                return self

            def run(self):
                obj.server.jsonrpc.runWatchers()
                return self

            @property
            def watched(self):
                return obj.server.jsonrpc.hasWatchedOnWindowsChange()

            @watched.setter
            def watched(self, b):
                """
                Args:
                    b: boolean
                """
                assert isinstance(b, bool)
                obj.server.jsonrpc.runWatchersOnWindowsChange(b)

        return Watchers()

    @property
    def info(self):
        return self.jsonrpc.deviceInfo()

    def __call__(self, **kwargs):
        return UiObject(self, Selector(**kwargs))


# Will be removed in the future
def wrap_wait_exists(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        timeout = kwargs.pop('timeout', self.wait_timeout)
        if not self.wait(timeout=timeout):
            raise UiObjectNotFoundError({
                'code': -32002,
                'message': E(self.selector.__str__())
            })
        return fn(self, *args, **kwargs)

    return inner


class UiObject(object):
    def __init__(self, session, selector):
        self.session = session
        self.selector = selector
        self.jsonrpc = session.jsonrpc

    @property
    def wait_timeout(self):
        return self.session.server.wait_timeout

    @property
    def exists(self):
        '''check if the object exists in current window.'''
        return Exists(self)

    @property
    @retry(
        UiObjectNotFoundError, delay=.5, tries=3, jitter=0.1, logger=logging)
    def info(self):
        '''ui object info.'''
        return self.jsonrpc.objInfo(self.selector)

    def click(self, timeout=None, offset=None):
        """
        Click UI element. 

        Args:
            timeout: seconds wait element show up
            offset: (xoff, yoff) default (0.5, 0.5) -> center

        The click method does the same logic as java uiautomator does.
        1. waitForExists 2. get VisibleBounds center 3. send click event

        Raises:
            UiObjectNotFoundError
        """
        self.must_wait(timeout=timeout)
        x, y = self.center(offset=offset)
        # ext.htmlreport need to comment bellow code
        # if info['clickable']:
        #     return self.jsonrpc.click(self.selector)
        self.session.click(x, y)
        delay = self.session.server.click_post_delay
        if delay:
            time.sleep(delay)

    def center(self, offset=None):
        """
        Args:
            offset: optional, (x_off, y_off)
                (0, 0) means center, (0.5, 0.5) means right-bottom
        Return:
            center point (x, y)
        """
        info = self.info
        bounds = info.get('visibleBounds') or info.get("bounds")
        lx, ly, rx, ry = bounds['left'], bounds['top'], bounds['right'], bounds['bottom']
        if not offset:
            offset = (0.5, 0.5)
        xoff, yoff = offset
        width, height = rx - lx, ry - ly
        x = lx + width * xoff
        y = ly + height * yoff
        return (x, y)

    def click_gone(self, maxretry=10, interval=1.0):
        """
        Click until element is gone

        Args:
            maxretry (int): max click times
            interval (float): sleep time between clicks

        Return:
            Bool if element is gone
        """
        self.click_exists()
        while maxretry > 0:
            time.sleep(interval)
            if not self.exists:
                return True
            self.click_exists()
            maxretry -= 1
        return False

    def click_exists(self, timeout=0):
        try:
            self.click(timeout=timeout)
            return True
        except UiObjectNotFoundError:
            return False

    def long_click(self, duration=None, timeout=None):
        """
        Args:
            duration (float): seconds of pressed
            timeout (float): seconds wait element show up
        """

        # if info['longClickable'] and not duration:
        #     return self.jsonrpc.longClick(self.selector)
        self.must_wait(timeout=timeout)
        x, y = self.center()
        return self.session.long_click(x, y, duration)

    def drag_to(self, *args, **kwargs):
        duration = kwargs.pop('duration', 0.5)
        timeout = kwargs.pop('timeout', None)
        self.must_wait(timeout=timeout)

        steps = int(duration * 200)
        if len(args) >= 2 or "x" in kwargs or "y" in kwargs:

            def drag2xy(x, y):
                x, y = self.session.pos_rel2abs(x,
                                                y)  # convert percent position
                return self.jsonrpc.dragTo(self.selector, x, y, steps)

            return drag2xy(*args, **kwargs)
        return self.jsonrpc.dragTo(self.selector, Selector(**kwargs), steps)

    def swipe(self, direction, steps=10):
        """
        Performs the swipe action on the UiObject.
        Swipe from center

        Args:
            direction (str): one of ("left", "right", "up", "down")
            steps (int): move steps, one step is about 5ms
            percent: float between [0, 1]

        Note: percent require API >= 18
        # assert 0 <= percent <= 1
        """
        assert direction in ("left", "right", "up", "down")

        self.must_wait()
        info = self.info
        bounds = info.get('visibleBounds') or info.get("bounds")
        lx, ly, rx, ry = bounds['left'], bounds['top'], bounds['right'], bounds['bottom']
        cx, cy = (lx+rx)//2, (ly+ry)//2
        if direction == 'up':
            self.session.swipe(cx, cy, cx, ly, steps=steps)
        elif direction == 'down':
            self.session.swipe(cx, cy, cx,  ry - 1, steps=steps)
        elif direction == 'left':
            self.session.swipe(cx, cy, lx, cy, steps=steps)
        elif direction == 'right':
            self.session.swipe(cx, cy, rx - 1, cy, steps=steps)

        # return self.jsonrpc.swipe(self.selector, direction, percent, steps)


    def gesture(self, start1, start2, end1, end2, steps=100):
        '''
        perform two point gesture.
        Usage:
        d().gesture(startPoint1, startPoint2, endPoint1, endPoint2, steps)
        '''
        rel2abs = self.session.pos_rel2abs

        def point(x=0, y=0):
            x, y = rel2abs(x, y)
            return {"x": x, "y": y}

        def ctp(pt):
            return point(*pt) if type(pt) == tuple else pt

        s1, s2, e1, e2 = ctp(start1), ctp(start2), ctp(end1), ctp(end2)
        return self.jsonrpc.gesture(self.selector, s1, s2, e1, e2, steps)

    def pinch_in(self, percent=100, steps=50):
        return self.jsonrpc.pinchIn(self.selector, percent, steps)

    def pinch_out(self, percent=100, steps=50):
        return self.jsonrpc.pinchOut(self.selector, percent, steps)

    def wait(self, exists=True, timeout=None):
        """
        Wait until UI Element exists or gone

        Args:
            timeout (float): wait element timeout

        Example:
            d(text="Clock").wait()
            d(text="Settings").wait("gone") # wait until it's gone
        """
        if timeout is None:
            timeout = self.wait_timeout
        http_wait = timeout + 10
        if exists:
            try:
                return self.jsonrpc.waitForExists(
                    self.selector, int(timeout * 1000), http_timeout=http_wait)
            except requests.ReadTimeout as e:
                warnings.warn("waitForExists readTimeout: %s" % e, RuntimeWarning)
                return self.exists()
        else:
            try:
                return self.jsonrpc.waitUntilGone(
                    self.selector, int(timeout * 1000), http_timeout=http_wait)
            except requests.ReadTimeout as e:
                warnings.warn("waitForExists readTimeout: %s" % e, RuntimeWarning)
                return not self.exists()

    def wait_gone(self, timeout=None):
        """ wait until ui gone
        Args:
            timeout (float): wait element gone timeout
        """
        timeout = timeout or self.wait_timeout
        return self.wait(exists=False, timeout=timeout)

    def must_wait(self, exists=True, timeout=None):
        """ wait and if not found raise UiObjectNotFoundError """
        if not self.wait(exists, timeout):
            raise UiObjectNotFoundError({'code': -32002, 'method': 'wait'})

    def send_keys(self, text):
        """ alias of set_text """
        return self.set_text(text)

    def set_text(self, text, timeout=None):
        self.must_wait(timeout=timeout)
        if not text:
            return self.jsonrpc.clearTextField(self.selector)
        else:
            return self.jsonrpc.setText(self.selector, text)

    def get_text(self, timeout=None):
        """ get text from field """
        self.must_wait(timeout=timeout)
        return self.jsonrpc.getText(self.selector)

    def clear_text(self, timeout=None):
        self.must_wait(timeout=timeout)
        return self.set_text(None)

    def child(self, **kwargs):
        return UiObject(self.session, self.selector.clone().child(**kwargs))

    def sibling(self, **kwargs):
        return UiObject(self.session, self.selector.clone().sibling(**kwargs))

    child_selector, from_parent = child, sibling

    def child_by_text(self, txt, **kwargs):
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByText(self.selector, Selector(**kwargs),
                                            txt, allow_scroll_search)
        else:
            name = self.jsonrpc.childByText(self.selector, Selector(**kwargs),
                                            txt)
        return UiObject(self.session, name)

    def child_by_description(self, txt, **kwargs):
        # need test
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByDescription(self.selector,
                                                   Selector(**kwargs), txt,
                                                   allow_scroll_search)
        else:
            name = self.jsonrpc.childByDescription(self.selector,
                                                   Selector(**kwargs), txt)
        return UiObject(self.session, name)

    def child_by_instance(self, inst, **kwargs):
        # need test
        return UiObject(self.session,
                        self.jsonrpc.childByInstance(self.selector,
                                                     Selector(**kwargs), inst))

    def parent(self):
        # android-uiautomator-server not implemented
        # In UIAutomator, UIObject2 has getParent() method
        # https://developer.android.com/reference/android/support/test/uiautomator/UiObject2.html
        raise NotImplementedError()
        return UiObject(self.session, self.jsonrpc.getParent(self.selector))

    def __getitem__(self, index):
        selector = self.selector.clone()
        selector.update_instance(index)
        return UiObject(self.session, selector)

    @property
    def count(self):
        return self.jsonrpc.count(self.selector)

    def __len__(self):
        return self.count

    def __iter__(self):
        obj, length = self, self.count

        class Iter(object):
            def __init__(self):
                self.index = -1

            def next(self):
                self.index += 1
                if self.index < length:
                    return obj[self.index]
                else:
                    raise StopIteration()

            __next__ = next

        return Iter()

    def right(self, **kwargs):
        def onrightof(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect2["left"] - rect1["right"] if top < bottom else -1

        return self.__view_beside(onrightof, **kwargs)

    def left(self, **kwargs):
        def onleftof(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect1["left"] - rect2["right"] if top < bottom else -1

        return self.__view_beside(onleftof, **kwargs)

    def up(self, **kwargs):
        def above(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect1["top"] - rect2["bottom"] if left < right else -1

        return self.__view_beside(above, **kwargs)

    def down(self, **kwargs):
        def under(rect1, rect2):
            left, top, right, bottom = intersect(rect1, rect2)
            return rect2["top"] - rect1["bottom"] if left < right else -1

        return self.__view_beside(under, **kwargs)

    def __view_beside(self, onsideof, **kwargs):
        bounds = self.info["bounds"]
        min_dist, found = -1, None
        for ui in UiObject(self.session, Selector(**kwargs)):
            dist = onsideof(bounds, ui.info["bounds"])
            if dist >= 0 and (min_dist < 0 or dist < min_dist):
                min_dist, found = dist, ui
        return found

    @property
    def fling(self):
        """
        Args:
            dimention (str): one of "vert", "vertically", "vertical", "horiz", "horizental", "horizentally"
            action (str): one of "forward", "backward", "toBeginning", "toEnd", "to"
        """
        jsonrpc = self.jsonrpc
        selector = self.selector

        class _Fling(object):
            def __init__(self):
                self.vertical = True
                self.action = 'forward'

            def __getattr__(self, key):
                if key in ["horiz", "horizental", "horizentally"]:
                    self.vertical = False
                    return self
                if key in ['vert', 'vertically', 'vertical']:
                    self.vertical = True
                    return self
                if key in [
                        "forward", "backward", "toBeginning", "toEnd", "to"
                ]:
                    self.action = key
                    return self
                raise ValueError("invalid prop %s" % key)

            def __call__(self, max_swipes=500, **kwargs):
                if self.action == "forward":
                    return jsonrpc.flingForward(selector, self.vertical)
                elif self.action == "backward":
                    return jsonrpc.flingBackward(selector, self.vertical)
                elif self.action == "toBeginning":
                    return jsonrpc.flingToBeginning(selector, self.vertical,
                                                    max_swipes)
                elif self.action == "toEnd":
                    return jsonrpc.flingToEnd(selector, self.vertical,
                                              max_swipes)

        return _Fling()

    @property
    def scroll(self):
        """
        Args:
            dimention (str): one of "vert", "vertically", "vertical", "horiz", "horizental", "horizentally"
            action (str): one of "forward", "backward", "toBeginning", "toEnd", "to"
        """
        selector = self.selector
        jsonrpc = self.jsonrpc

        class _Scroll(object):
            def __init__(self):
                self.vertical = True
                self.action = 'forward'

            def __getattr__(self, key):
                if key in ["horiz", "horizental", "horizentally"]:
                    self.vertical = False
                    return self
                if key in ['vert', 'vertically', 'vertical']:
                    self.vertical = True
                    return self
                if key in [
                        "forward", "backward", "toBeginning", "toEnd", "to"
                ]:
                    self.action = key
                    return self
                raise ValueError("invalid prop %s" % key)

            def __call__(self, steps=20, max_swipes=500, **kwargs):
                if self.action in ["forward", "backward"]:
                    method = jsonrpc.scrollForward if self.action == "forward" else jsonrpc.scrollBackward
                    return method(selector, self.vertical, steps)
                elif self.action == "toBeginning":
                    return jsonrpc.scrollToBeginning(selector, self.vertical,
                                                     max_swipes, steps)
                elif self.action == "toEnd":
                    return jsonrpc.scrollToEnd(selector, self.vertical,
                                               max_swipes, steps)
                elif self.action == "to":
                    return jsonrpc.scrollTo(selector, Selector(**kwargs),
                                            self.vertical)

        return _Scroll()


class Selector(dict):
    """The class is to build parameters for UiSelector passed to Android device.
    """
    __fields = {
        "text": (0x01, None),  # MASK_TEXT,
        "textContains": (0x02, None),  # MASK_TEXTCONTAINS,
        "textMatches": (0x04, None),  # MASK_TEXTMATCHES,
        "textStartsWith": (0x08, None),  # MASK_TEXTSTARTSWITH,
        "className": (0x10, None),  # MASK_CLASSNAME
        "classNameMatches": (0x20, None),  # MASK_CLASSNAMEMATCHES
        "description": (0x40, None),  # MASK_DESCRIPTION
        "descriptionContains": (0x80, None),  # MASK_DESCRIPTIONCONTAINS
        "descriptionMatches": (0x0100, None),  # MASK_DESCRIPTIONMATCHES
        "descriptionStartsWith": (0x0200, None),  # MASK_DESCRIPTIONSTARTSWITH
        "checkable": (0x0400, False),  # MASK_CHECKABLE
        "checked": (0x0800, False),  # MASK_CHECKED
        "clickable": (0x1000, False),  # MASK_CLICKABLE
        "longClickable": (0x2000, False),  # MASK_LONGCLICKABLE,
        "scrollable": (0x4000, False),  # MASK_SCROLLABLE,
        "enabled": (0x8000, False),  # MASK_ENABLED,
        "focusable": (0x010000, False),  # MASK_FOCUSABLE,
        "focused": (0x020000, False),  # MASK_FOCUSED,
        "selected": (0x040000, False),  # MASK_SELECTED,
        "packageName": (0x080000, None),  # MASK_PACKAGENAME,
        "packageNameMatches": (0x100000, None),  # MASK_PACKAGENAMEMATCHES,
        "resourceId": (0x200000, None),  # MASK_RESOURCEID,
        "resourceIdMatches": (0x400000, None),  # MASK_RESOURCEIDMATCHES,
        "index": (0x800000, 0),  # MASK_INDEX,
        "instance": (0x01000000, 0)  # MASK_INSTANCE,
    }
    __mask, __childOrSibling, __childOrSiblingSelector = "mask", "childOrSibling", "childOrSiblingSelector"

    def __init__(self, **kwargs):
        super(Selector, self).__setitem__(self.__mask, 0)
        super(Selector, self).__setitem__(self.__childOrSibling, [])
        super(Selector, self).__setitem__(self.__childOrSiblingSelector, [])
        for k in kwargs:
            self[k] = kwargs[k]

    def __str__(self):
        """ remove useless part for easily debugger """
        selector = self.copy()
        selector.pop('mask')
        for key in ('childOrSibling', 'childOrSiblingSelector'):
            if not selector.get(key):
                selector.pop(key)
        args = []
        for (k, v) in selector.items():
            args.append(k + '=' + repr(v))
        return 'Selector [' + ', '.join(args) + ']'

    def __setitem__(self, k, v):
        if k in self.__fields:
            super(Selector, self).__setitem__(U(k), U(v))
            super(Selector, self).__setitem__(
                self.__mask, self[self.__mask] | self.__fields[k][0])
        else:
            raise ReferenceError("%s is not allowed." % k)

    def __delitem__(self, k):
        if k in self.__fields:
            super(Selector, self).__delitem__(k)
            super(Selector, self).__setitem__(
                self.__mask, self[self.__mask] & ~self.__fields[k][0])

    def clone(self):
        kwargs = dict((k, self[k]) for k in self if k not in [
            self.__mask, self.__childOrSibling, self.__childOrSiblingSelector
        ])
        selector = Selector(**kwargs)
        for v in self[self.__childOrSibling]:
            selector[self.__childOrSibling].append(v)
        for s in self[self.__childOrSiblingSelector]:
            selector[self.__childOrSiblingSelector].append(s.clone())
        return selector

    def child(self, **kwargs):
        self[self.__childOrSibling].append("child")
        self[self.__childOrSiblingSelector].append(Selector(**kwargs))
        return self

    def sibling(self, **kwargs):
        self[self.__childOrSibling].append("sibling")
        self[self.__childOrSiblingSelector].append(Selector(**kwargs))
        return self

    def update_instance(self, i):
        # update inside child instance
        if self[self.__childOrSiblingSelector]:
            self[self.__childOrSiblingSelector][-1]['instance'] = i
        else:
            self['instance'] = i


class Exists(object):
    """Exists object with magic methods."""

    def __init__(self, uiobject):
        self.uiobject = uiobject

    def __nonzero__(self):
        """Magic method for bool(self) python2 """
        return self.uiobject.jsonrpc.exist(self.uiobject.selector)

    def __bool__(self):
        """ Magic method for bool(self) python3 """
        return self.__nonzero__()

    def __call__(self, timeout=0):
        """Magic method for self(args).

        Args:
            timeout (float): exists in seconds
        """
        if timeout:
            return self.uiobject.wait(timeout=timeout)
        return bool(self)

    def __repr__(self):
        return str(bool(self))


class XPathSelector(object):
    def __init__(self, xpath, server, source=None):
        self.xpath = xpath
        self.server = server
        self.source = source

    def wait(self, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            elements = self.all()
            if elements:
                return elements[0]
            time.sleep(.5)

    def click(self, timeout=10.0):
        """
        click element
        """
        elem = self.wait(timeout=timeout)
        if not elem:
            raise UiaError(self.xpath)
        x, y = elem.center()
        self.server.click(x, y)

    def all(self):
        """
        Returns:
            list of XMLElement
        """
        xml_content = self.source or self.server.dump_hierarchy()
        return [
            XMLElement(node)
            for node in simplexml.xpath_findall(self.xpath, xml_content)
        ]

    @property
    def exists(self):
        return len(self.all()) > 0


class XMLElement(object):
    def __init__(self, elem):
        self.elem = elem

    def center(self):
        bounds = self.elem.attrib.get("bounds")
        lx, ly, rx, ry = map(int, re.findall(r"\d+", bounds))
        return (lx + rx) // 2, (ly + ry) // 2

    @property
    def text(self):
        return self.elem.attrib.get("text")

    @property
    def attrib(self):
        return self.elem.attrib


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
