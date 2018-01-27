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
import xml.dom.minidom
import xml.etree.ElementTree as ET
import threading
import shutil
import warnings
from datetime import datetime
from subprocess import list2cmdline

import six
import humanize
from retry import retry

if six.PY2:
    import urlparse
    FileNotFoundError = OSError
else: # for py3
    import urllib.parse as urlparse

import requests
import uiautomator2.adbutils as adbutils

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
        }
        if errcode in m:
            return m[errcode]
        if errcode >= -32099 and errcode <= -32000:
            return 'Server error'
        return 'Unknown error'

    def __init__(self, error={}):
        self.code = error.get('code')
        self.message = error.get('message')
        self.data = error.get('data')
        self.exception_name = (self.data or {}).get('exceptionTypeName', 'Unknown')

    def __str__(self):
        return '%d %s: %s' % (
            self.code,
            self.format_errcode(self.code),
            '%s <%s>' % (self.exception_name, self.message))
    
    def __repr__(self):
        return repr(str(self))


class SessionBrokenError(UiaError):
    pass

class UiObjectNotFoundError(JsonRpcError):
    pass


def log_print(s):
    thread_name = threading.current_thread().getName()
    print(thread_name + ": " + datetime.now().strftime('%H:%M:%S,%f')[:-3] + " " + s)


def intersect(rect1, rect2):
    top = rect1["top"] if rect1["top"] > rect2["top"] else rect2["top"]
    bottom = rect1["bottom"] if rect1["bottom"] < rect2["bottom"] else rect2["bottom"]
    left = rect1["left"] if rect1["left"] > rect2["left"] else rect2["left"]
    right = rect1["right"] if rect1["right"] < rect2["right"] else rect2["right"]
    return left, top, right, bottom


def U(x):
    if six.PY3:
        return x
    return x.decode('utf-8') if type(x) is str else x


def connect(addr=None):
    """
    Args:
        addr (str): uiautomator server address or serial number. default from env-var ANDROID_DEVICE_IP

    Example:
        connect("10.0.0.1:7912")
        connect("10.0.0.1") # use default 7912 port
        connect("http://10.0.0.1")
        connect("http://10.0.0.1:7912")
        connect("cff1123ea")  # adb device serial number
    """
    if not addr or addr == '+':
        addr = os.getenv('ANDROID_DEVICE_IP')
    if addr and re.match(r"(http://)?(\d+\.\d+\.\d+\.\d+)(:\d+)?", addr):
        return connect_wifi(addr)
    return connect_usb(addr)


def connect_wifi(addr=None):
    """
    Args:
        addr (str) uiautomator server address.
    
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
    """
    client = adbutils.Client()
    adb = client.device(serial)
    lport = adb.forward_port(7912)
    return connect_wifi('127.0.0.1:'+str(lport))


class TimeoutRequestsSession(requests.Session):
    def request(self, method, url, **kwargs):
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = HTTP_TIMEOUT
        verbose = hasattr(self, 'debug') and self.debug
        if verbose:
            data = kwargs.get('data') or ''
            if isinstance(data, dict):
                data = 'dict:' + json.dumps(data)
            print(datetime.now().strftime("%H:%M:%S.%f")[:-3], "$ curl -X {method} -d '{data}' '{url}'".format(
                method=method, url=url, data=data.decode()
            ))
        resp = super(TimeoutRequestsSession, self).request(method, url, **kwargs)
        if verbose:
            print(datetime.now().strftime("%H:%M:%S.%f")[:-3], "Response >>>\n"+resp.text.rstrip()+"\n<<< END")
        return resp


class UIAutomatorServer(object):
    __isfrozen = False

    def __init__(self, host, port=7912, healthCheck=False):
        self._host = host
        self._port = port
        self._reqsess = TimeoutRequestsSession() # use requests.Session to enable HTTP Keep-Alive
        self._server_url = 'http://{}:{}'.format(host, port)
        self._server_jsonrpc_url = self._server_url + "/jsonrpc/0"
        self._default_session = Session(self, None)
        self.__devinfo = None
        self.platform = None # hot fix for weditor

        self.wait_timeout = 20.0 # wait element timeout
        self.click_post_delay = None # wait after each click

        # prevent creating new attrs
        self._freeze()

        # check if server is alive
        if healthCheck: self.healthcheck()

    def _freeze(self):
        self.__isfrozen = True

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
    def debug(self):
        return hasattr(self._reqsess, 'debug') and self._reqsess.debug

    @debug.setter
    def debug(self, value):
        self._reqsess.debug = bool(value)
    
    def path2url(self, path):
        return urlparse.urljoin(self._server_url, path)

    # deprecated
    # TODO: remove in 0.1.4
    def set_click_post_delay(self, seconds):
        """
        Set delay seconds after click

        Args:
            seconds (float): seconds
        """
        warnings.warn("Deprecated, will remove in 0.1.4 Use d.click_post_delay = ? instead", DeprecationWarning, stacklevel=2)
        self.click_post_delay = seconds
    
    def window_size(self):
        """ return (width, height) """
        info = self._reqsess.get(self.path2url('/info')).json()
        return info['display']['width'], info['display']['height']

    @property
    def jsonrpc(self):
        """
        Make jsonrpc call easier
        For example:
            self.jsonrpc.pressKey("home")
        """
        class JSONRpcWrapper():
            def __init__(self, server):
                self.server = server
                self.method = None
            
            def __getattr__(self, method):
                self.method = method
                return self

            def __call__(self, *args, **kwargs):
                http_timeout = kwargs.pop('http_timeout', HTTP_TIMEOUT)
                params = args if args else kwargs
                return self.server.jsonrpc_retry_call(self.method, params, http_timeout)

        return JSONRpcWrapper(self)

    def jsonrpc_retry_call(self, *args, **kwargs): #method, params=[], http_timeout=60):
        try:
            return self.jsonrpc_call(*args, **kwargs)
        except (GatewayError,):
            warnings.warn("uiautomator2 is down, try to restarted.", RuntimeWarning, stacklevel=1)
            # for XiaoMi, want to recover uiautomator2 must start app:com.github.uiautomator
            self.healthcheck(unlock=False)
            return self.jsonrpc_call(*args, **kwargs)

    def jsonrpc_call(self, method, params=[], http_timeout=60):
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
        res = self._reqsess.post(self._server_jsonrpc_url,
            headers={"Content-Type": "application/json"},
            timeout=http_timeout,
            data=data)
        if DEBUG:
            print("Shell$ curl -X POST -d '{}' {}".format(data, self._server_jsonrpc_url))
            print("Output> " + res.text)
        if res.status_code == 502:
            raise GatewayError(res, "gateway error, time used %.1fs" % (time.time() - request_start))
        if res.status_code != 200:
            raise UiaError(self._server_jsonrpc_url, data, res.status_code, res.text, "HTTP Return code is not 200", res.text)
        jsondata = res.json()
        error = jsondata.get('error')
        if not error:
            return jsondata.get('result')

        # error happends
        err = JsonRpcError(error)
        if 'UiObjectNotFoundException' in err.exception_name:
            err.__class__ = UiObjectNotFoundError
        raise err
    
    def _jsonrpc_id(self, method):
        m = hashlib.md5()
        m.update(("%s at %f" % (method, time.time())).encode("utf-8"))
        return m.hexdigest()
    
    def touch_action(self, x, y):
        """
        Returns:
            TouchAction
        """
        raise NotImplementedError()
    
    @property
    def alive(self):
        try:
            r = self._reqsess.get(self.path2url('/ping'), timeout=2)
            return r.status_code == 200
        except requests.exceptions.ReadTimeout:
            return False

    def healthcheck(self, unlock=True):
        """
        Check if uiautomator is running, if not launch again
        
        Raises:
            RuntimeError
        """
        if unlock:
            self.open_identify()
        wait = not unlock # should not wait IdentifyActivity open or it will stuck sometimes
        self.app_start('com.github.uiautomator', '.MainActivity', wait=wait, stop=True)

        # launch atx-agent uiautomator keeper
        self._reqsess.post(self.path2url('/uiautomator'))

        # wait until uiautomator2 service working
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self.alive:
                # keyevent BACK if current is com.github.uiautomator
                # XiaoMi uiautomator will kill the app(com.github.uiautomator) when launch
                #   it is better to start a service to make uiautomator live longer
                if self.current_app()['package'] != 'com.github.uiautomator':
                    self.adb_shell('am', 'startservice', '-n', 'com.github.uiautomator/.Service')
                    time.sleep(.5)
                    return True
                else:
                    time.sleep(0.5)
                    self.adb_shell('input', 'keyevent', 'BACK')
                    return True
            time.sleep(.5)
        raise RuntimeError("Uiautomator started failed.")

    def app_install_remote(self, filepath, verify_hook=None):
        """
        Args:
            filepath(str): apk path on the device
        
        Raises:
            RuntimeError
        """
        r = self._reqsess.post(self.path2url("/install"), data={"filepath": filepath})
        if r.status_code != 200:
            raise RuntimeError("app install error:", r.text)
        id = r.text.strip()
        interval = 1.0 # 2.0s
        next_refresh = time.time()
        while True:
            if time.time() < next_refresh:
                time.sleep(.2)
                continue
            ret = self._reqsess.get(self.path2url('/install/'+id))
            progress = None
            try:
                progress = ret.json()
            except:
                raise RuntimeError("invalid json response:", ret.text)
            message = progress.get('message')
            if progress.get('error'):
                raise RuntimeError(progress.get('error'), progress.get('message'))
            elif message == 'apk parsing':
                next_refresh = time.time() + interval
            elif message == 'installing':
                next_refresh = time.time() + interval*2
                if callable(verify_hook):
                    verify_hook(self)
            elif message == 'success installed':
                log_print("Successfully installed")
                return progress.get('extraData')

            log_print(message)


    def app_install(self, url, verify_hook=None):
        """
        {u'message': u'downloading', u'id': u'2', u'titalSize': 407992690, u'copiedSize': 49152}

        Returns:
            packageName

        Raises:
            RuntimeError
        """
        r = self._reqsess.post(self.path2url('/install'), data={'url': url})
        if r.status_code != 200:
            raise RuntimeError("app install error:", r.text)
        id = r.text.strip()
        interval = 1.0 # 2.0s
        next_refresh = time.time()
        while True:
            if time.time() < next_refresh:
                time.sleep(.2)
                continue
            ret = self._reqsess.get(self.path2url('/install/'+id))
            progress = None
            try:
                progress = ret.json()
            except:
                raise RuntimeError("invalid json response:", ret.text)
            total_size = progress.get('totalSize') or progress.get('titalSize')
            copied_size = progress.get('copiedSize')
            message = progress.get('message')
            if message == 'downloading':
                next_refresh = time.time() + interval
            elif message == 'installing':
                next_refresh = time.time() + interval*2
                if callable(verify_hook):
                    verify_hook(self)

            if progress.get('error'):
                raise RuntimeError(progress.get('error'), progress.get('message'))
            log_print("{} {} / {}".format(
                progress.get('message'),
                humanize.naturalsize(copied_size),
                humanize.naturalsize(total_size)))
            if message == 'success installed':
                return progress.get('extraData')
    
    def dump_hierarchy(self, compressed=False, pretty=False):
        content = self.jsonrpc.dumpWindowHierarchy(compressed, None)
        if pretty and "\n " not in content:
            xml_text = xml.dom.minidom.parseString(content.encode("utf-8"))
            content = U(xml_text.toprettyxml(indent='  '))
        return content

    def adb_shell(self, *args):
        """
        Example:
            adb_shell('pwd')
            adb_shell('ls', '-l')
            adb_shell('ls -l')

        Returns:
            a UTF-8 encoded string for stdout merged with stderr, after the entire shell command is completed.
        """
        cmdline = args[0] if len(args) == 1 else list2cmdline(args)
        ret = self._reqsess.post(self.path2url('/shell'), data={'command': cmdline})
        if ret.status_code != 200:
            raise RuntimeError("device agent responds with an error code %d" % ret.status_code)
        return ret.json().get('output')
    
    def app_start(self, pkg_name, activity=None, extras={}, wait=True, stop=False, unlock=False):
        """ Launch application
        Args:
            pkg_name (str): package name
            activity (str): app activity
            stop (str): Stop app before starting the activity. (require activity)
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
            args = ['am', 'start']
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
            self.adb_shell(*args) #'am', 'start', '-W', '-n', '{}/{}'.format(pkg_name, activity))
        else:
            if stop:
                self.app_stop(pkg_name)
            self.adb_shell('monkey', '-p', pkg_name, '-c', 'android.intent.category.LAUNCHER', '1')
    
    def current_app(self):
        """
        Return: dict(package, activity, pid?)
        """
        # try: adb shell dumpsys activity top
        _activityRE = re.compile(r'ACTIVITY (?P<package>[^/]+)/(?P<activity>[^/\s]+) \w+ pid=(?P<pid>\d+)')
        m = _activityRE.search(self.adb_shell('dumpsys', 'activity', 'top'))
        if m:
            return dict(package=m.group('package'), activity=m.group('activity'), pid=int(m.group('pid')))

        # try: adb shell dumpsys window windows
        _focusedRE = re.compile('mFocusedApp=.*ActivityRecord{\w+ \w+ (?P<package>.*)/(?P<activity>.*) .*')
        m = _focusedRE.search(self.adb_shell('dumpsys', 'window', 'windows'))
        if m:
            return dict(package=m.group('package'), activity=m.group('activity'))
        # empty result
        warnings.warn("Couldn't get focused app", stacklevel=2)
        return dict(package=None, activity=None)

    def app_stop(self, pkg_name):
        """ Stop one application: am force-stop"""
        self.adb_shell('am', 'force-stop', pkg_name)
    
    def app_stop_all(self, excludes=[]):
        """ Stop all applications
        Args:
            excludes (list): apps that do now want to kill
        
        Returns:
            a list of killed apps
        """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        pkgs = re.findall('package:([^\s]+)', self.adb_shell('pm', 'list', 'packages', '-3'))
        process_names = re.findall('([^\s]+)$', self.adb_shell('ps'), re.M)
        kill_pkgs = set(pkgs).intersection(process_names).difference(our_apps + excludes)
        kill_pkgs = list(kill_pkgs)
        for pkg_name in kill_pkgs:
            self.app_stop(pkg_name)
        return kill_pkgs

    def app_clear(self, pkg_name):
        """ Stop and clear app data: pm clear """
        self.adb_shell('pm', 'clear', pkg_name)
    
    def app_uninstall(self, pkg_name):
        """ Uninstall an app """
        self.adb_shell("pm", "uninstall", pkg_name)
    
    def app_uninstall_all(self, excludes=[], verbose=False):
        """ Uninstall all apps """
        our_apps = ['com.github.uiautomator', 'com.github.uiautomator.test']
        pkgs = re.findall('package:([^\s]+)', self.adb_shell('pm', 'list', 'packages', '-3'))
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
        self.adb_shell('am', 'start', '-W', '-n', 'com.github.uiautomator/.IdentifyActivity', '-e', 'theme', theme)

    def _pidof_app(self, pkg_name):
        return self.adb_shell('pidof', pkg_name).strip()

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
        r = self._reqsess.post(self.path2url('/download'), data={'url': url, 'filepath': dst, 'mode': modestr})
        if r.status_code != 200:
            raise IOError("push-url", "%s -> %s" % (url, dst), r.text)
        key = r.text.strip()
        while 1:
            r = self._reqsess.get(self.path2url('/download/'+key))
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
                        message,
                        humanize.naturalsize(copied_size),
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
        r = self._reqsess.post(pathname, data={'mode': modestr}, files={'file': src})
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

    def session(self, pkg_name):
        """
        Context context = InstrumentationRegistry.getInstrumentation().getContext();
        Intent intent = context.getPackageManager().getLaunchIntentForPackage(YOUR_APP_PACKAGE_NAME);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK);
        context.startActivity(intent);

        It is also possible to get pid, and use pid to get package name
        """
        self.app_start(pkg_name)
        time.sleep(0.5)
        pid = self._pidof_app(pkg_name)
        if not pid:
            raise SessionBrokenError(pkg_name)
        return Session(self, pkg_name, pid)
        # raise NotImplementedError()

    def dismiss_apps(self):
        """
        UiDevice.getInstance().pressRecentApps();
        UiObject recentapp = new UiObject(new UiSelector().resourceId("com.android.systemui:id/dismiss_task"));
        """
        raise NotImplementedError()
        self.press("recent")
    
    def __getattr__(self, attr):
        return getattr(self._default_session, attr)

    def __call__(self, **kwargs):
        return self._default_session(**kwargs)


def check_alive(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not self._check_alive():
            raise SessionBrokenError(self._pkg_name)
        return fn(self, *args, **kwargs)
    return inner


class Session(object):
    __orientation = (  # device orientation
        (0, "natural", "n", 0),
        (1, "left", "l", 90),
        (2, "upsidedown", "u", 180),
        (3, "right", "r", 270)
    )

    def __init__(self, server, pkg_name=None, pid=None):
        self.server = server
        self._pkg_name = pkg_name
        self._pid = pid

    def _check_alive(self):
        if self._pid is None:
            return True
        return self.server.adb_shell('pidof', self._pkg_name).strip() == self._pid

    @property
    @check_alive
    def jsonrpc(self):
        return self.server.jsonrpc

    @property
    def pos_rel2abs(self):
        info = {}
        def convert(x, y):
            if (0 < x < 1 or 0 < y < 1) and not info:
                uiautomator_info = self.info
                display = self.server.device_info.get('display', {})
                if display:
                    w, h = display['width'], display['height']
                    rotation = uiautomator_info['displayRotation']
                    if rotation in [1, 3]:
                        w, h = h, w
                    info['displayWidth'] = w
                    info['displayHeight'] = h
                else:
                    info.update(uiautomator_info)
            if x < 1:
                x = int(info['displayWidth'] * x)
            if y < 1:
                y = int(info['displayHeight'] * y)
            return x, y
        return convert

    def set_fastinput_ime(self, enable=True):
        """ Enable of Disable FastInputIME """
        fast_ime = 'com.github.uiautomator/.FastInputIME'
        if enable:
            self.server.adb_shell('ime', 'enable', fast_ime)
            self.server.adb_shell('ime', 'set', fast_ime)
        else:
            self.server.adb_shell('ime', 'disable', fast_ime)

    def send_keys(self, text):
        """
        Raises:
            EnvironmentError
        """
        self.wait_fastinput_ime()
        base64text = base64.b64encode(text.encode('utf-8')).decode()
        self.server.adb_shell('am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'text', base64text)

    def clear_text(self):
        """ clear text
        Raises:
            EnvironmentError
        """
        self.wait_fastinput_ime()
        self.server.adb_shell('am', 'broadcast', '-a', 'ADB_CLEAR_TEXT')
    
    def wait_fastinput_ime(self, timeout=5.0):
        """ wait FastInputIME is ready
        Args:
            timeout(float): maxium wait time
        Raises:
            EnvironmentError
        """
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
        dim = self.server.adb_shell('dumpsys', 'input_method')
        m = _INPUT_METHOD_RE.search(dim)
        method_id = None if not m else m.group(1)
        shown = "mInputShown=true" in dim
        return (method_id, shown)

    def tap(self, x, y):
        """
        Tap position
        """
        x, y = self.pos_rel2abs(x, y)
        ret = self.jsonrpc.click(x, y)
        if self.server.click_post_delay:
            time.sleep(self.server.click_post_delay)
    
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
        Alias of tap
        """
        return self.tap(x, y)
    
    def long_click(self, x, y, duration=0.5):
        '''long click at arbitrary coordinates.'''
        x, y = self.pos_rel2abs(x, y)
        self.touch.down(x, y)
        time.sleep(duration)
        self.touch.up(x, y)
        return self
    
    def swipe(self, fx, fy, tx, ty, duration=0.5):
        """
        Args:
            fx, fy: from position
            tx, ty: to position
            duration (float): duration
        
        Documents:
            uiautomator use steps instead of duration
            As the document say: Each step execution is throttled to 5ms per step.
        
        Links:
            https://developer.android.com/reference/android/support/test/uiautomator/UiDevice.html#swipe%28int,%20int,%20int,%20int,%20int%29
        """
        rel2abs = self.pos_rel2abs
        fx, fy = rel2abs(fx, fy)
        tx, ty = rel2abs(tx, ty)
        return self.jsonrpc.swipe(fx, fy, tx, ty, int(duration*200))
    
    def swipe_points(self, points, duration=0.5):
        ppoints = []
        rel2abs = self.pos_rel2abs
        for p in points:
            x, y = rel2abs(p[0], p[1])
            ppoints.append(x)
            ppoints.append(y)
        return self.jsonrpc.swipePoints(ppoints, int(duration*200))

    def drag(self, sx, sy, ex, ey, duration=0.5):
        '''Swipe from one point to another point.'''
        rel2abs = self.pos_rel2abs
        sx, sy = rel2abs(sx, sy)
        ex, ey = rel2abs(ex, ey)
        return self.jsonrpc.drag(sx, sy, ex, ey, int(duration*200))

    @retry(IOError, delay=.5, tries=5)
    def screenshot(self, filename=None, format='pillow'):
        """
        Image format is JPEG

        Args:
            filename (str): saved filename
            format (string): used when filename is empty. one of "pillow" or "opencv"
        
        Raises:
            IOError

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
            return self.jsonrpc.pressKeyCode(key, meta) if meta else self.server.jsonrpc.pressKeyCode(key)
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

    # @orientation.setter
    # def orientation(self, value):
    
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

    def xpath_findall(self, xpath):
        xml = self.server.dump_hierarchy()
        root = ET.fromstring(xml)
        return root.findall(xpath)

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
                obj.server.jsonrpc.registerClickUiObjectWatcher(name, self.__selectors, Selector(**kwargs))

            def press(self, *keys):
                """
                key (str): on of
                    ("home", "back", "left", "right", "up", "down", "center",
                    "search", "enter", "delete", "del", "recent", "volume_up",
                    "menu", "volume_down", "volume_mute", "camera", "power")
                """
                obj.server.jsonrpc.registerPressKeyskWatcher(name, self.__selectors, keys)
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
        return Watchers()

    @property
    def info(self):
        return self.jsonrpc.deviceInfo()

    def __call__(self, **kwargs):
        return UiObject(self, Selector(**kwargs))


def wait_exists_wrap(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        self.wait(timeout=self.wait_timeout)
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
        return self.jsonrpc.exist(self.selector)

    @property
    def info(self):
        '''ui object info.'''
        return self.jsonrpc.objInfo(self.selector)

    @wait_exists_wrap
    def tap(self):
        '''
        click on the ui object.
        Usage:
        d(text="Clock").click()  # click on the center of the ui object
        '''
        self.click_nowait()

    def click_nowait(self): # todo, the java layer wait a little longer(10s)
        """
        Tap element with no wait

        Raises:
            UiObjectNotFoundError
        """
        self.jsonrpc.click(self.selector)
        post_delay = self.session.server.click_post_delay
        if post_delay:
            time.sleep(post_delay)

    def click(self):
        """ Alias of tap """
        return self.tap()

    def click_exists(self, timeout=0):
        if not self.wait(timeout=timeout):
            return False
        try:
            self.click_nowait()
            return True
        except UiObjectNotFoundError:
                return False
    
    @wait_exists_wrap
    def long_click(self):
        info = self.info
        if info['longClickable']:
            return self.jsonrpc.longClick(self.selector)
        bounds = info.get("visibleBounds") or info.get("bounds")
        x = (bounds["left"] + bounds["right"]) / 2
        y = (bounds["top"] + bounds["bottom"]) / 2
        return self.session.long_click(x, y)

    @wait_exists_wrap
    def drag_to(self, *args, **kwargs):
        duration = kwargs.pop('duration', 0.5)
        steps = int(duration*200)
        if len(args) >= 2 or "x" in kwargs or "y" in kwargs:
            def drag2xy(x, y):
                x, y = self.session.pos_rel2abs(x, y) # convert percent position
                return self.jsonrpc.dragTo(self.selector, x, y, steps)
            return drag2xy(*args, **kwargs)
        return self.jsonrpc.dragTo(self.selector, Selector(**kwargs), steps)

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
        timeout = timeout or self.wait_timeout
        http_wait = timeout + 10
        if exists:
            return self.jsonrpc.waitForExists(self.selector, int(timeout*1000), http_timeout=http_wait)
        else:
            return self.jsonrpc.waitUntilGone(self.selector, int(timeout*1000), http_timeout=http_wait)
    
    def wait_gone(self, timeout=None):
        """ wait until ui gone
        Args:
            timeout (float): wait element gone timeout
        """
        timeout = timeout or self.wait_timeout
        return self.wait(exists=False, timeout=timeout)
    
    def send_keys(self, text):
        """ alias of set_text """
        return self.set_text(text)

    @wait_exists_wrap
    def set_text(self, text):
        if not text:
            return self.jsonrpc.clearTextField(self.selector)
        else:
            return self.jsonrpc.setText(self.selector, text)
    
    @wait_exists_wrap
    def clear_text(self):
        return self.set_text(None)

    def child(self, **kwargs):
        return UiObject(
            self.session,
            self.selector.clone().child(**kwargs)
        )

    def sibling(self, **kwargs):
        return UiObject(
            self.session, 
            self.selector.clone().sibling(**kwargs)
        )
    
    child_selector, from_parent = child, sibling
    
    def child_by_text(self, txt, **kwargs):
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByText(
                self.selector,
                Selector(**kwargs),
                txt,
                allow_scroll_search
            )
        else:
            name = self.jsonrpc.childByText(
                self.selector,
                Selector(**kwargs),
                txt
            )
        return UiObject(self.session, name)

    def child_by_description(self, txt, **kwargs):
        # need test
        if "allow_scroll_search" in kwargs:
            allow_scroll_search = kwargs.pop("allow_scroll_search")
            name = self.jsonrpc.childByDescription(
                self.selector,
                Selector(**kwargs),
                txt,
                allow_scroll_search
            )
        else:
            name = self.jsonrpc.childByDescription(
                self.selector,
                Selector(**kwargs),
                txt
            )
        return UiObject(self.session, name)

    def child_by_instance(self, inst, **kwargs):
        # need test
        return UiObject(
            self.session,
            self.jsonrpc.childByInstance(self.selector, Selector(**kwargs), inst)
        )
    
    def parent(self):
        # android-uiautomator-server not implemented
        # In UIAutomator, UIObject2 has getParent() method
        # https://developer.android.com/reference/android/support/test/uiautomator/UiObject2.html
        raise NotImplementedError()
        return UiObject(
            self.session,
            self.jsonrpc.getParent(self.selector)
        )

    def __getitem__(self, index):
        selector = self.selector.clone()
        selector['instance'] = index
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
                if key in ["forward", "backward", "toBeginning", "toEnd", "to"]:
                    self.action = key
                    return self
                raise ValueError("invalid prop %s" % key)
            
            def __call__(self, max_swipes=500, **kwargs):
                if self.action == "forward":
                    return jsonrpc.flingForward(selector, self.vertical)
                elif self.action == "backward":
                    return jsonrpc.flingBackward(selector, self.vertical)
                elif self.action == "toBeginning":
                    return jsonrpc.flingToBeginning(selector, self.vertical, max_swipes)
                elif self.action == "toEnd":
                    return jsonrpc.flingToEnd(selector, self.vertical, max_swipes)
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
                if key in ["forward", "backward", "toBeginning", "toEnd", "to"]:
                    self.action = key
                    return self
                raise ValueError("invalid prop %s" % key)
            
            def __call__(self, steps=20, max_swipes=500, **kwargs):
                if self.action in ["forward", "backward"]:
                    method = jsonrpc.scrollForward if self.action == "forward" else jsonrpc.scrollBackward
                    return method(selector, self.vertical, steps)
                elif self.action == "toBeginning":
                    return jsonrpc.scrollToBeginning(selector, self.vertical, max_swipes, steps)
                elif self.action == "toEnd":
                    return jsonrpc.scrollToEnd(selector, self.vertical, max_swipes, steps)
                elif self.action == "to":
                    return jsonrpc.scrollTo(selector, Selector(**kwargs), self.vertical)
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

    def __setitem__(self, k, v):
        if k in self.__fields:
            super(Selector, self).__setitem__(U(k), U(v))
            super(Selector, self).__setitem__(self.__mask, self[self.__mask] | self.__fields[k][0])
        else:
            raise ReferenceError("%s is not allowed." % k)

    def __delitem__(self, k):
        if k in self.__fields:
            super(Selector, self).__delitem__(k)
            super(Selector, self).__setitem__(self.__mask, self[self.__mask] & ~self.__fields[k][0])

    def clone(self):
        kwargs = dict((k, self[k]) for k in self
                      if k not in [self.__mask, self.__childOrSibling, self.__childOrSiblingSelector])
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
