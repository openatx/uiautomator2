# coding: utf-8
#

import threading
import time

import pytest

from uiautomator2 import utils


def test_list2cmdline():
    testdata = [
        [("echo", "hello"), "echo hello"],
        [("echo", "hello&world"), "echo 'hello&world'"],
        [("What's", "your", "name?"), """'What'"'"'s' your 'name?'"""]
    ]
    for args, expect in testdata:
        cmdline = utils.list2cmdline(args)
        assert cmdline == expect, "Args: %s, Expect: %s, Got: %s" % (args, expect, cmdline)


def test_inject_call():
    def foo(a, b, c=2):
        return a*100+b*10+c
    
    ret = utils.inject_call(foo, a=2, b=4)
    assert ret == 242

    with pytest.raises(TypeError):
        utils.inject_call(foo, 2)


def test_threadsafe_wrapper():
    class A:
        n = 0

        @utils.thread_safe_wrapper
        def call(self):
            v = self.n
            time.sleep(.5)
            self.n = v + 1
    
    a = A()
    th1 = threading.Thread(name="th1", target=a.call)
    th2 = threading.Thread(name="th2", target=a.call)
    th1.start()
    th2.start()
    th1.join()
    th2.join()
    
    assert 2 == a.n


def test_is_version_compatiable():
    assert utils.is_version_compatiable("1.0.0", "1.0.0")
    assert utils.is_version_compatiable("1.0.0", "1.0.1")
    assert utils.is_version_compatiable("1.0.0", "1.2.0")
    assert utils.is_version_compatiable("1.0.1", "1.1.0")

    assert not utils.is_version_compatiable("1.0.1", "2.1.0")
    assert not utils.is_version_compatiable("1.3.1", "1.3.0")
    assert not utils.is_version_compatiable("1.3.1", "1.2.0")
    assert not utils.is_version_compatiable("1.3.1", "1.2.2")
