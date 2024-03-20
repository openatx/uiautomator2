# coding: utf-8
#

import functools
import inspect
import os
import shlex
import threading
import typing
from typing import Union

import filelock

from ._proto import Direction
from .exceptions import SessionBrokenError, UiObjectNotFoundError


def check_alive(fn):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not self.running():
            raise SessionBrokenError(self._pkg_name)
        return fn(self, *args, **kwargs)

    return inner


_cached_values = {}


def cache_return(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        key = (fn, args, frozenset(kwargs.items()))
        value = _cached_values.get(key)
        if value is not None:
            return value

        _cached_values[key] = ret = fn(*args, **kwargs)
        return ret

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
                'message': self.selector.__str__()
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


def list2cmdline(args: Union[list, tuple]):
    return ' '.join(list(map(shlex.quote, args)))


def inject_call(fn, *args, **kwargs):
    """
    Call function without known all the arguments

    Args:
        fn: function
        args: arguments
        kwargs: key-values
    
    Returns:
        as the fn returns
    """
    assert callable(fn), "first argument must be callable"

    st = inspect.signature(fn)
    fn_kwargs = {
        key: kwargs[key]
        for key in st.parameters.keys() if key in kwargs
    }
    ba = st.bind(*args, **fn_kwargs)
    ba.apply_defaults()
    return fn(*ba.args, **ba.kwargs)


class ProgressReader:
    def __init__(self, rd):
        pass

    def read(self, size=-1):
        pass


def natualsize(size: int):
    _KB = 1 << 10
    _MB = 1 << 20
    _GB = 1 << 30

    if size >= _GB:
        return '{:.1f} GB'.format(size / _GB)
    elif size >= _MB:
        return '{:.1f} MB'.format(size / _MB)
    else:
        return '{:.1f} KB'.format(size / _KB)


def swipe_in_bounds(d: "uiautomator2.Device",
                    bounds: list,
                    direction: Union[Direction, str],
                    scale: float = 0.6):
    """
    Args:
        d: Device object
        bounds: list of [lx, ly, rx, ry]
        direction: one of ["left", "right", "up", "down"]
        scale: percent of swipe, range (0, 1.0)
    
    Raises:
        AssertionError, ValueError
    """
    def _swipe(_from, _to):
        print("SWIPE", _from, _to)
        d.swipe(_from[0], _from[1], _to[0], _to[1])

    assert 0 < scale <= 1.0
    assert len(bounds) == 4

    lx, ly, rx, ry = bounds
    width, height = rx - lx, ry - ly

    h_offset = int(width * (1 - scale)) // 2
    v_offset = int(height * (1 - scale)) // 2

    left = lx + h_offset, ly + height // 2
    up = lx + width // 2, ly + v_offset
    right = rx - h_offset, ly + height // 2
    bottom = lx + width // 2, ry - v_offset

    if direction == Direction.LEFT:
        _swipe(right, left)
    elif direction == Direction.RIGHT:
        _swipe(left, right)
    elif direction == Direction.UP:
        _swipe(bottom, up)
    elif direction == Direction.DOWN:
        _swipe(up, bottom)
    else:
        raise ValueError("Unknown direction:", direction)


def thread_safe_wrapper(fn: typing.Callable):
    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not hasattr(self, "_lock"):
            self._lock = threading.Lock()

        with self._lock:
            return fn(self, *args, **kwargs)
    
    return inner


def process_safe_wrapper(fn: typing.Callable[..., typing.Any]) -> typing.Callable[..., typing.Any]:
    """
    threadsafe for process calls
    """
    lockfile_path = os.path.expanduser("~/.uiautomator2/" + fn.__name__ + ".lock")
    flock = filelock.FileLock(lockfile_path, timeout=120) # default timeout

    @functools.wraps(fn)
    def inner(self, *args, **kwargs):
        if not hasattr(self, "_plock"):
            self._plock = flock

        with self._plock:
            return fn(self, *args, **kwargs)
    
    return inner


if __name__ == "__main__":
    for n in (1, 10000, 10000000, 10000000000):
        print(n, natualsize(n))
