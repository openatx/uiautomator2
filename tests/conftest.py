# coding: utf-8

import uiautomator2 as u2
import pytest


@pytest.fixture(scope="module")
def d():
    _d = u2.connect()
    _d.settings['operation_delay'] = (0.2, 0.2)
    _d.settings['operation_delay_methods'] = ['click', 'swipe']
    return _d


@pytest.fixture
def package_name():
    return "io.appium.android.apis"


@pytest.fixture(scope="function")
def sess(d, package_name) -> u2.Device:
    d.watcher.reset()
    
    d.app_start(package_name, stop=True)
    yield d


