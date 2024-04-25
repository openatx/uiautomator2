# coding: utf-8
#

import uiautomator2 as u2

def test_session_function_exists(dev: u2.Device):
    dev.wlan_ip
    dev.watcher
    dev.jsonrpc
    dev.shell
    dev.settings
    dev.xpath


def test_session_app(dev: u2.Device, package_name):
    dev.app_start(package_name)
    assert dev.app_current()['package'] == package_name

    dev.app_wait(package_name)
    assert package_name in dev.app_list()
    assert package_name in dev.app_list_running()

    # assert sess.app_info(package_name)['packageName'] == package_name


def test_session_window_size(dev: u2.Device):
    assert isinstance(dev.window_size(), tuple)

