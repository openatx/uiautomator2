# coding: utf-8
#

import pytest
import uiautomator2 as u2
from uiautomator2.exceptions import SessionBrokenError

def test_session_function_exists(dev: u2.Device):
    dev.wlan_ip
    dev.watcher
    dev.jsonrpc
    dev.shell
    dev.settings
    dev.xpath


def test_app_mixin(dev: u2.Device, package_name: str):
    assert package_name in dev.app_list()
    dev.app_stop(package_name)
    assert package_name not in dev.app_list_running()
    dev.app_start(package_name)
    assert package_name in dev.app_list_running()
    
    demo_pid = dev.app_wait(package_name)
    current_info = dev.app_current()
    assert demo_pid == current_info['pid']
    assert current_info['package'] == package_name

    dev.app_start(package_name, stop=True)
    assert demo_pid != dev.app_wait(package_name)


def test_session_app(dev: u2.Device, package_name):
    dev.app_start(package_name)
    assert dev.app_current()['package'] == package_name

    dev.app_wait(package_name)
    assert package_name in dev.app_list()
    assert package_name in dev.app_list_running()

    with dev.session("io.appium.android.apis") as sess:
        sess(text="App").click()
        assert sess.running() is True
        dev.app_stop("io.appium.android.apis")
        assert sess.running() is False
        with pytest.raises(SessionBrokenError):
            sess(text="App").click()
    
    with dev.session("io.appium.android.apis") as sess:
        sess(text="App").click()
        assert sess.running() is True


def test_session_window_size(dev: u2.Device):
    assert isinstance(dev.window_size(), tuple)


def test_auto_grant_permissions(dev: u2.Device):
    dev.app_auto_grant_permissions("io.appium.android.apis")

