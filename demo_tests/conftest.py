# coding: utf-8
# author: codeskyblue

import pytest
import uiautomator2 as u2


@pytest.fixture(scope="function")
def d():
    _d = u2.connect_usb()
    _d.press("home")
    yield _d
    

@pytest.fixture(scope="function")
def app(d: u2.Device):
    d.app_start("com.example.u2testdemo", stop=True)
    d(text="Addition").wait()
    yield d