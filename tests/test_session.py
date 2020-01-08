# coding: utf-8
#

from collections import namedtuple


def test_session(sess):
    sess.wlan_ip
    sess.widget
    sess.watcher
    sess.image
    sess.jsonrpc
    sess.open_identify
    sess.shell
    sess.set_new_command_timeout
    sess.settings
    sess.taobao
    sess.xpath


def test_session_app(sess, package_name):
    sess.app_start(package_name)
    assert sess.app_current()['package'] == package_name

    sess.app_wait(package_name)
    assert package_name in sess.app_list()
    assert package_name in sess.app_list_running()

    assert sess.app_info(package_name)['packageName'] == package_name

def test_session_window_size(sess):
    assert isinstance(sess.window_size(), tuple)

