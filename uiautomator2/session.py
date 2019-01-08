# coding: utf-8
#

from __future__ import absolute_import, print_function

import base64
import io
import logging
import re
import time
import warnings
import xml.dom.minidom

import requests
import six
from retry import retry

from uiautomator2.exceptions import (NullPointerExceptionError,
                                     UiObjectNotFoundError)
from uiautomator2.utils import Exists, U, check_alive, hooks_wrap, intersect

_INPUT_METHOD_RE = re.compile(r'mCurMethodId=([-_./\w]+)')


_fail_prompt_enabled = False


def set_fail_prompt(enable=True):
    """
    When Element click through Exception, Prompt user to decide
    """
    global _fail_prompt_enabled
    _fail_prompt_enabled = enable


def _failprompt(fn):
    def _inner(self, *args, **kwargs):
        if not _fail_prompt_enabled:
            return fn(self, *args, **kwargs)

        from uiautomator2 import messagebox
        try:
            return fn(self, *args, **kwargs)
        except UiObjectNotFoundError as e:
            result = messagebox.retryskipabort(str(e), 30)
            if result == 'retry':
                return _inner(self, *args, **kwargs)
            elif result == 'skip':
                return True
            else:
                raise
    return _inner


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

            def up(self, x=0, y=0):
                """ ACTION_UP x, y seems no use """
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
        # self.touch.move(x, y) # maybe can fix 
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

    @property
    def xpath(self):
        return self.server.ext_xpath

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

    @_failprompt
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
                warnings.warn("waitForExists readTimeout: %s" %
                              e, RuntimeWarning)
                return self.exists()
        else:
            try:
                return self.jsonrpc.waitUntilGone(
                    self.selector, int(timeout * 1000), http_timeout=http_wait)
            except requests.ReadTimeout as e:
                warnings.warn("waitForExists readTimeout: %s" %
                              e, RuntimeWarning)
                return not self.exists()

    def wait_gone(self, timeout=None):
        """ wait until ui gone
        Args:
            timeout (float): wait element gone timeout

        Returns:
            bool if element gone
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
        # return UiObject(self.session, self.jsonrpc.getParent(self.selector))

    def __getitem__(self, index):
        """
        Raises:
            IndexError
        """
        if isinstance(self.selector, six.string_types):
            raise IndexError(
                "Index is not supported when UiObject returned by child_by_xxx")
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
