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

from uiautomator2.version import __atx_agent_version__
from uiautomator2 import adbutils
import requests

import hashlib
import time
import functools
import json
import io
import os
import re
import sys
import shutil
import threading
import warnings
from datetime import datetime
from subprocess import list2cmdline
from collections import namedtuple

import six
import humanize
import progress.bar
from retry import retry
import six.moves.urllib.parse as urlparse
from uiautomator2.exceptions import (
    UiaError,
    UiObjectNotFoundError,
    SessionBrokenError,
    GatewayError,
    JsonRpcError,
    UiAutomationNotConnectedError,
    NullObjectExceptionError,
    NullPointerExceptionError,
    StaleObjectExceptionError,
)
from uiautomator2.session import (  # noqa: F401
    Session, set_fail_prompt,
)

if six.PY2:
    FileNotFoundError = OSError

DEBUG = False
HTTP_TIMEOUT = 60


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


def _is_wifi_addr(addr):
    if not addr:
        return False
    if re.match(r"^https?://", addr):
        return True
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", addr)
    if m and m.group(1) != "127.0.0.1":
        return True
    return False


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
    adb = adbutils.AdbClient()
    if not serial:
        device = adb.must_one_device()
    else:
        device = adbutils.AdbDevice(adb, serial)
    # adb = adbutils.Adb(serial)
    lport = device.forward_port(7912)
    d = connect_wifi('127.0.0.1:' + str(lport))
    if not d.agent_alive:
        warnings.warn("backend atx-agent is not alive, start again ...",
                      RuntimeWarning)
        # TODO: /data/local/tmp might not be execuable and atx-agent can be somewhere else
        device.shell_output("/data/local/tmp/atx-agent", "server", "-d")
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
            data = kwargs.get('data') or '""'
            if isinstance(data, dict):
                data = json.dumps(data)
            time_start = time.time()
            print(
                datetime.now().strftime("%H:%M:%S.%f")[:-3],
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
                print(
                    datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "Response (%d ms) >>>\n" % (
                        (time.time() - time_start) * 1000) +
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
        except (NullObjectExceptionError, NullPointerExceptionError,
                StaleObjectExceptionError) as e:
            if args[1] != 'dumpWindowHierarchy':  # args[1] method
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
            raise UiaError(jsonrpc_url, data, res.status_code, res.text,
                           "HTTP Return code is not 200", res.text)
        jsondata = res.json()
        error = jsondata.get('error')
        if not error:
            return jsondata.get('result')

        # error happends
        err = JsonRpcError(error, method)

        if isinstance(
                err.data,
                six.string_types) and 'UiAutomation not connected' in err.data:
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
        # self.app_start(  # may also stuck here.
        #     'com.github.uiautomator',
        #     '.MainActivity',
        #     wait=False,
        #     stop=True)
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
            args = [
                'am', 'start', '-a', 'android.intent.action.MAIN', '-c',
                'android.intent.category.LAUNCHER'
            ]
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
            r'mCurrentFocus=Window{.*\s+(?P<package>[^\s]+)/(?P<activity>[^\s]+)\}'
        )
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
            current_activity = self.current_app().get('activity')
            if activity == current_activity:
                return True
            time.sleep(.5)
        return False

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
        kill_pkgs = set(pkgs).intersection(process_names).difference(our_apps +
                                                                     excludes)
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
        url = self.path2url('/packages/{0}/info'.format(pkg_name))
        resp = self._reqsess.get(url)
        resp.raise_for_status()
        resp = resp.json()
        if not resp.get('success'):
            raise UiaError(resp.get('description', 'unknown'))
        return resp.get('data')

    def app_icon(self, pkg_name):
        """
        Returns:
            PIL.Image

        Raises:
            UiaError
        """
        from PIL import Image
        url = self.path2url('/packages/{0}/icon'.format(pkg_name))
        resp = self._reqsess.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content))

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

    def session(self, pkg_name=None, attach=False, launch_timeout=None):
        """
        Create a new session

        Args:
            pkg_name (str): android package name
            attach (bool): attach to already running app
            launch_timeout (int): launch timeout

        Raises:
            requests.HTTPError, SessionBrokenError
        """
        if pkg_name is None:
            return self._default_session

        if not attach:
            request_data = {"flags": "-W -S"}
            if launch_timeout:
                request_data["timeout"] = str(launch_timeout)
            resp = self._reqsess.post(
                self.path2url("/session/" + pkg_name), data=request_data)
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
                    raise ValueError(
                        "plugin \"%s\" not registed" % plugin_name)
            func, args, kwargs = self.__plugins[plugin_name]
            obj = functools.partial(func, self)(*args, **kwargs)
            self._cached_plugins[attr] = obj
            return obj
        try:
            return getattr(self._default_session, attr)
        except AttributeError:
            raise AttributeError(
                "'Session or UIAutomatorServer' object has no attribute '%s'" %
                attr)

    def __call__(self, **kwargs):
        return self._default_session(**kwargs)


# class XPathSelector(object):
#     def __init__(self, xpath, server, source=None):
#         self.xpath = xpath
#         self.server = server
#         self.source = source

#     def wait(self, timeout=10.0):
#         deadline = time.time() + timeout
#         while time.time() < deadline:
#             elements = self.all()
#             if elements:
#                 return elements[0]
#             time.sleep(.5)

#     def click(self, timeout=10.0):
#         """
#         click element
#         """
#         elem = self.wait(timeout=timeout)
#         if not elem:
#             raise UiaError(self.xpath)
#         x, y = elem.center()
#         self.server.click(x, y)

#     def all(self):
#         """
#         Returns:
#             list of XMLElement
#         """
#         xml_content = self.source or self.server.dump_hierarchy()
#         return [
#             XMLElement(node)
#             for node in simplexml.xpath_findall(self.xpath, xml_content)
#         ]

#     @property
#     def exists(self):
#         return len(self.all()) > 0

# class XMLElement(object):
#     def __init__(self, elem):
#         self.elem = elem

#     def center(self):
#         bounds = self.elem.attrib.get("bounds")
#         lx, ly, rx, ry = map(int, re.findall(r"\d+", bounds))
#         return (lx + rx) // 2, (ly + ry) // 2

#     @property
#     def text(self):
#         return self.elem.attrib.get("text")

#     @property
#     def attrib(self):
#         return self.elem.attrib


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
