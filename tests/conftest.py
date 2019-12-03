# coding: utf-8

import uiautomator2 as u2
import pytest


@pytest.fixture(scope="module")
def d():
    return u2.connect()


@pytest.fixture(scope="function")
def sess(d) -> u2.Session:
    d.watcher.reset()
    
    s = d.session("io.appium.android.apis")
    yield s