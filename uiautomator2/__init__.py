#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function

import hashlib
import time
import datetime
import functools
import json
import io
import os
import re
import xml.dom.minidom
import xml.etree.ElementTree as ET
import threading
import shutil

import six
import humanize
from subprocess import list2cmdline

if six.PY2:
    import urlparse
else: # for py3
    import urllib.parse as urlparse

import requests
from uiautomator2 import adbutils

DEBUG = False


class UiaError(Exception):
    pass

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
    print(thread_name + ": " + datetime.datetime.now().strftime('%H:%M:%S,%f')[:-3] + " " + s)


def U(x):
    if six.PY3:
        return x
    return x.decode('utf-8') if type(x) is str else x


def connect(addr=None):
    """
    Args:
        addr (str): uiautomator server address. default from env-var ANDROID_DEVICE_IP
    
    Example:
        connect("10.0.0.1")
    """
    if not addr:
        addr = os.getenv('ANDROID_DEVICE_IP') or '127.0.0.1'
    if '://' not in addr:
        addr = 'http://' + addr
    if addr.startswith('http://'):
        u = urlparse.urlparse(addr)
        host = u.hostname
        port = u.port or 7912
        return AutomatorServer(host, port)
    else:
        raise RuntimeError("address should startswith http://")


def connect_usb(serial=None):
    adb = adbutils.Adb(serial)
    lport = adb.forward_port(7912)
    return connect('127.0.0.1:'+str(lport))


class AutomatorServer(object):
    def __init__(self, host, port=7912):
        self._host = host
        self._port = port
        self._reqsess = requests.Session() # use HTTP Keep-Alive to speed request
        self._server_url = 'http://{}:{}'.format(host, port)
        self._server_jsonrpc_url = self._server_url + "/jsonrpc/0"
        self._default_session = Session(self, None)
        self._click_post_delay = None
        # TODO: check if server alive

    def path2url(self, path):
        return urlparse.urljoin(self._server_url, path)

    def set_click_post_delay(self, seconds):
        """
        Set delay seconds after click

        Args:
            seconds (float): seconds
        """
        self._click_post_delay = seconds

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
                params = args if args else kwargs
                return self.server.jsonrpc_call(self.method, params)
        
        return JSONRpcWrapper(self)

    def jsonrpc_call(self, method, params=[]):
        """ jsonrpc2 call
        Refs:
            - http://www.jsonrpc.org/specification
        """
        data = {
            "jsonrpc": "2.0",
            "id": self._jsonrpc_id(method),
            "method": method,
            "params": params,
        }
        data = json.dumps(data).encode('utf-8')
        res = self._reqsess.post(self._server_jsonrpc_url,
            headers={"Content-Type": "application/json"},
            timeout=60,
            data=data)
        if DEBUG:
            print("Shell$ curl -X POST -d '{}' {}".format(data, self._server_jsonrpc_url))
            print("Output> " + res.text)
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
    
    def healthcheck(self):
        """
        Check if uiautomator is running, if not launch again
        """
        return self._reqsess.post(self.path2url('/uiautomator')).text

    def app_install(self, url):
        """
        {u'message': u'downloading', u'id': u'2', u'titalSize': 407992690, u'copiedSize': 49152}

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
            log_print("{} {} / {}".format(
                progress.get('message'),
                humanize.naturalsize(copied_size),
                humanize.naturalsize(total_size)))
            if progress.get('error'):
                raise RuntimeError(progress.get('error'), progress.get('message'))
            if message == 'success installed':
                break
        return True
    
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
            shell output
        """
        cmdline = args[0] if len(args) == 1 else list2cmdline(args)
        ret = self._reqsess.post(self.path2url('/shell'), data={'command': cmdline})
        if ret.status_code != 200:
            raise RuntimeError("expect status 200, but got %d" % ret.status_code)
        return ret.json().get('output')
    
    def app_start(self, pkg_name, activity=None, stop=False):
        """ Launch application
        Args:
            pkg_name (str): package name
            activity (str): app activity
            stop (str): Stop app before starting the activity. (require activity)
        """
        if activity:
            # -D: enable debugging
            # -W: wait for launch to complete
            # -S: force stop the target app before starting the activity
            # --user <USER_ID> | current: Specify which user to run as; if not
            #    specified then run as the current user.
            args = ['am', 'start', '-W']
            if stop:
                args.append('-S')
            args += ['-n', '{}/{}'.format(pkg_name, activity)]
            self.adb_shell(*args) #'am', 'start', '-W', '-n', '{}/{}'.format(pkg_name, activity))
        else:
            if stop:
                self.app_stop(pkg_name)
            self.adb_shell('monkey', '-p', pkg_name, '-c', 'android.intent.category.LAUNCHER', '1')
    
    def app_stop(self, pkg_name):
        """ Stop application: am force-stop"""
        self.adb_shell('am', 'force-stop', pkg_name)
    
    def app_stop_all(self, excludes=[]):
        """ Stop all applications
        Args:
            excludes (list): apps that do now want to kill
        
        Returns:
            list of apps that been killed
        """
        pkgs = re.findall('package:([^\s]+)', self.adb_shell('pm', 'list', 'packages', '-3'))
        process_names = re.findall('([^\s]+)$', self.adb_shell('ps'), re.M)
        kill_pkgs = set(pkgs).intersection(process_names).difference(['com.github.uiautomator'] + excludes)
        kill_pkgs = list(kill_pkgs)
        for pkg_name in kill_pkgs:
            self.app_stop(pkg_name)
        return kill_pkgs

    def app_clear(self, pkg_name):
        """ Stop and clear app data: pm clear """
        self.adb_shell('pm', 'clear', pkg_name)
    
    def unlock(self):
        """ unlock screen """
        self.adb_shell('am', 'start', '-W', '-a', 'com.github.uiautomator.ACTION_IDENTIFY')
        self._default_session.press("home")

    def _pidof_app(self, pkg_name):
        return self.adb_shell('pidof', pkg_name).strip()
    
    def push(self, src, dst, mode=0o644):
        """
        Args:
            src (path or fileobj): source file
            dst (str): destination can be folder or file path
        
        Returns:
            dict object, for example:
                
                {"mode":"0660","size":63,"target":"/sdcard/ABOUT.rst"}
            
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
            FileNotFoundError

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

    def pos_rel2abs(self, x, y):
        info = None
        if x < 1 or y < 1:
            info = self.info
        if x < 1:
            x = int(info['displayWidth'] * x)
        if y < 1:
            y = int(info['displayHeight'] * y)
        return x, y

    def tap(self, x, y):
        """
        Tap position
        """
        x, y = self.pos_rel2abs(x, y)
        ret = self.jsonrpc.click(x, y)
        if self.server._click_post_delay:
            time.sleep(self.server._click_post_delay)

    def click(self, x, y):
        """
        Alias of tap
        """
        return self.tap(x, y)
    
    def long_click(self, x, y, duration=0.5):
        '''long click at arbitrary coordinates.'''
        x, y = self.pos_rel2abs(x, y)
        return self.swipe(x, y, x + 1, y + 1, duration)
    
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
        fx, fy = self.pos_rel2abs(fx, fy)
        tx, ty = self.pos_rel2abs(tx, ty)
        return self.jsonrpc.swipe(fx, fy, tx, ty, int(duration*200))
    
    def swipe_points(self, points, duration=0.5):
        ppoints = []
        for p in points:
            ppoints.append(p[0])
            ppoints.append(p[1])
        return self.jsonrpc.swipePoints(ppoints, int(duration)*200)

    def drag(self, sx, sy, ex, ey, duration=0.5):
        '''Swipe from one point to another point.'''
        sx, sy = self.pos_rel2abs(sx, sy)
        ex, ey = self.pos_rel2abs(ex, ey)
        return self.jsonrpc.drag(sx, sy, ex, ey, int(duration*200))

    def screenshot(self, filename=None):
        """
        Image format is PNG
        """
        r = requests.get(self.server.screenshot_uri)
        if filename:
            with open(filename, 'wb') as f:
                f.write(r.content)
            return filename
        else:
            from PIL import Image
            buff = io.BytesIO(r.content)
            return Image.open(buff)

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
        self.wait_timeout = 20

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
        self.tap_nowait()

    def tap_nowait(self): # todo, the java layer wait a little longer(10s)
        """
        Tap element with no wait

        Raises:
            UiObjectNotFoundError
        """
        self.jsonrpc.click(self.selector)
        post_delay = self.session.server._click_post_delay
        if post_delay:
            time.sleep(post_delay)

    def click(self):
        """ Alias of tap """
        return self.tap()

    def click_exists(self, timeout=0):
        if not self.wait(timeout=timeout):
            return False
        try:
            self.tap_nowait()
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
                return self.jsonrpc.dragTo(self.selector, x, y, steps)
            return drag2xy(*args, **kwargs)
        return self.jsonrpc.dragTo(self.selector, Selector(**kwargs), steps)

    def wait(self, exists=True, timeout=10.0):
        """
        Wait until UI Element exists or gone
        
        Example:
            d(text="Clock").wait()
            d(text="Settings").wait("gone") # wait until it's gone
        """
        if exists:
            return self.jsonrpc.waitForExists(self.selector, int(timeout*1000))
        else:
            return self.jsonrpc.waitUntilGone(self.selector, int(timeout*1000))
    
    def wait_gone(self, timeout=10.0):
        """ wait until ui gone """
        return self.wait(exists=False)
    
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
    
    def __getitem__(self, index):
        selector = self.selector.clone()
        selector['instance'] = index
        return UiObject(self.session, selector)    


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

    child_selector, from_parent = child, sibling