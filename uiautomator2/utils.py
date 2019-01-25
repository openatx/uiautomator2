# coding: utf-8
#

import six
import functools

from uiautomator2.exceptions import (
    SessionBrokenError,
    UiObjectNotFoundError)


def U(x):
    if six.PY3:
        return x
    return x.decode('utf-8') if type(x) is str else x


def E(x):
    if six.PY3:
        return x
    return x.encode('utf-8') if type(x) is unicode else x


def check_alive(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not self.running():
            raise SessionBrokenError(self._pkg_name)
        return fn(self, *args, **kwargs)

    return inner


def hooks_wrap(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        name = fn.__name__.lstrip('_')
        self.server.hooks_apply("before", name, args, kwargs, None)
        ret = fn(self, *args, **kwargs)
        self.server.hooks_apply("after", name, args, kwargs, ret)
    return inner


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


def intersect(rect1, rect2):
    top = rect1["top"] if rect1["top"] > rect2["top"] else rect2["top"]
    bottom = rect1["bottom"] if rect1["bottom"] < rect2["bottom"] else rect2[
        "bottom"]
    left = rect1["left"] if rect1["left"] > rect2["left"] else rect2["left"]
    right = rect1["right"] if rect1["right"] < rect2["right"] else rect2[
        "right"]
    return left, top, right, bottom


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
