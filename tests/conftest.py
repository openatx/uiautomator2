# coding: utf-8

import uiautomator2 as u2
import pytest


@pytest.fixture(scope="module")
def d():
    _d = u2.connect()
    _d.settings['click_before_delay'] = .2
    _d.settings['click_after_delay'] = .2
    return _d


@pytest.fixture(scope="function")
def sess(d) -> u2.Session:
    d.watcher.reset()
    
    s = d.session("io.appium.android.apis")
    yield s


@pytest.fixture
def package_name():
    return "io.appium.android.apis"