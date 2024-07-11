# coding: utf-8
# author: codeskyblue

import time
import pytest
import uiautomator2 as u2


@pytest.fixture(scope='function')
def dev():
    d = u2.connect_usb()
    d.debug = True
    package = 'com.example.u2testdemo'
    d.app_start(package, stop=True)
    yield d
    # d.app_stop(package)


def test_toast(dev: u2.Device):
    dev.clear_toast()
    assert dev.last_toast is None
    
    dev(text="Toast").click()
    dev(text="Show Toast").click()
    time.sleep(.1)
    assert dev.last_toast == 'Button Clicked!'
    