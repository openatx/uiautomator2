#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function

import hashlib
import time
import functools
import six
import requests


DEBUG = False


class UiaError(Exception):
    pass

class UiaRpcError(UiaError):
    pass

class UiaSessionBrokeError(UiaError):
    pass


def U(x):
    if six.PY3:
        return x
    return x.decode('utf-8') if type(x) is str else x


def stringfy_jsonrpc_errcode(errcode):
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


class AutomatorServer(object):
    def __init__(self):
        self._reqsess = requests.Session() # use HTTP Keep-Alive to speed request
        self._server_url = "http://10.0.0.1:7912/jsonrpc/0"

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
        res = self._reqsess.post(self._server_url,
            headers={"Content-Type": "application/json"},
            timeout=10,
            data=data)
        if res.status_code != 200:
            raise UiaError(self._server_url, data, res.status_code, "HTTP Return code is not 200")
        jsondata = res.json()
        if jsondata.get('error'):
            error = jsondata.get('error')
            code, message, data = error.get('code'), error.get('message'), error.get('data')
            if -32099 <= code <= -32000: # Server error
                raise UiaRpcError(stringfy_jsonrpc_errcode(code), code, message, data)
    
    def _jsonrpc_id(self, method):
        m = hashlib.md5()
        m.update(("%s at %f" % (method, time.time())).encode("utf-8"))
        return m.hexdigest()
    
    def touch_action(self, x, y):
        """
        Returns:
            TouchAction
        """
        pass
    
    def dump_hierarchy(self, compressed=False, pretty=True):
        pass
    
    def session(self, pkg_name):
        """
        Context context = InstrumentationRegistry.getInstrumentation().getContext();
        Intent intent = context.getPackageManager().getLaunchIntentForPackage(YOUR_APP_PACKAGE_NAME);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK);
        context.startActivity(intent);

        It is also possible to get pid, and use pid to get package name
        """
        pass

    def dismiss_apps(self):
        """
        UiDevice.getInstance().pressRecentApps();
        UiObject recentapp = new UiObject(new UiSelector().resourceId("com.android.systemui:id/dismiss_task"));
        """
        pass


class JsonRpcClient(object):
    def __init__(self, )
    def __getattr__(self, method):


def check_alive(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not self._check_alive():
            raise UiaSessionBrokeError(self._pkg_name)
        return fn(self, *args, **kwargs)
    return inner


class Session(object):
    def __init__(self, server, pkg_name):
        self.server = server
        self._pkg_name = pkg_name

    def _check_alive(self):
        return True

    @property
    @check_alive
    def jsonrpc(self):
        return self.server.jsonrpc

    @check_alive
    def tap(self, x, y):
        """
        Tap position
        """
        return self.server.jsonrpc.click(x, y)

    def click(self, x, y):
        """
        Alias of tap
        """
        return self.tap(x, y)
    
    @check_alive
    def swipe(self, lx, ly, rx, ry, duration=0.5):
        """
        Args:
            lx, ly: from position
            rx, ry: to position
            duration (float): duration
        """
        pass
    
    def screenshot(self, filename=None):
        """
        Image format is PNG
        """
        pass
    
    def press(self, key):
        """
        press key via name or key code. Supported key name includes:
            home, back, left, right, up, down, center, menu, search, enter,
            delete(or del), recent(recent apps), volume_up, volume_down,
            volume_mute, camera, power.
        """
        return self.server.jsonrpc.pressKey(key)

    @property
    def info(self):
        return self.server.jsonrpc.deviceInfo()

    def __call__(self, **kwargs):
        return UiObject(self, Selector(**kwargs))


def wait_exists(fn):
    @functools.wraps(fn):
    def inner(self, *args, **kwargs):
        self.wait(self.wait_timeout)
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

    @wait_exists
    def tap(self):
        '''
        click on the ui object.
        Usage:
        d(text="Clock").click()  # click on the center of the ui object
        '''
        return self.jsonrpc.click(self.selector)

    def click(self):
        """ Alias of tap """
        return self.tap()

    def wait(self, status='exists'):
        """
        Wait until UI Element exists or gone
        
        Example:
            d(text="Clock").wait()
            d(text="Settings").wait("gone") # wait until it's gone
        """
        if status == 'exists':
            return self.jsonrpc.waitForExists(self.selector)
        elif status == 'gone':
            return self.jsonrpc.waitUntilGone(self.selector)
        else:
            raise ValueError("status can only be exists or gone")
    
    @wait_exists
    def set_text(self, text):
        if not text:
            return self.jsonrpc.clearTextField(self.selector)
        else:
            return self.jsonrpc.setText(self.selector, text)
    
    @wait_exists
    def clear_text(self):
        return self.set_text(None)


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