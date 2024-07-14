# coding: utf-8
#

import threading
import time

import pytest
from PIL import Image

from uiautomator2 import utils


def test_list2cmdline():
    testdata = [
        [("echo", "hello"), "echo hello"],
        [("echo", "hello&world"), "echo 'hello&world'"],
        [("What's", "your", "name?"), """'What'"'"'s' your 'name?'"""],
        ["echo hello", "echo hello"],
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


def test_naturalsize():
    assert utils.natualsize(1) == "0.0 KB"
    assert utils.natualsize(1024) == "1.0 KB"
    assert utils.natualsize(1<<20) == "1.0 MB"
    assert utils.natualsize(1<<30) == "1.0 GB"


def test_image_convert():
    im = Image.new("RGB", (100, 100))
    im2 = utils.image_convert(im, "pillow")
    assert isinstance(im2, Image.Image)
    
    with pytest.raises(ValueError):
        utils.image_convert(im, "unknown")


def test_depreacated():
    @utils.deprecated("use bar instead")
    def foo():
        pass

    with pytest.warns(DeprecationWarning):
        foo()