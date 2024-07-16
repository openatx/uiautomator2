# coding: utf-8
# author: codeskyblue

import pytest
import uiautomator2 as u2


PACKAGE = "com.example.u2testdemo"


def test_wait_activity(d: u2.Device):
    # assert app.wait_activity('.MainActivity', timeout=10)
    
    d.app_start(PACKAGE, activity=".AdditionActivity", wait=True)
    assert d.wait_activity('.AdditionActivity', timeout=3)
    assert not d.wait_activity('.NotExistActivity', timeout=1)


def test_app_wait(app: u2.Device):
    assert app.app_wait(PACKAGE, front=True)


def test_app_start_stop(d: u2.Device):
    assert PACKAGE in d.app_list()
    d.app_stop(PACKAGE)
    assert PACKAGE not in d.app_list_running()
    d.app_start(PACKAGE, wait=True)
    assert PACKAGE in d.app_list_running()
    

def test_app_clear(d: u2.Device):
    d.app_clear(PACKAGE)
    # d.app_stop_all()


def test_app_info(d: u2.Device):
    d.app_info(PACKAGE)
    with pytest.raises(u2.AppNotFoundError):
        d.app_info("not.exist.package")


def test_auto_grant_permissions(d: u2.Device):
    d.app_auto_grant_permissions(PACKAGE)


def test_session(d: u2.Device):
    app = d.session(PACKAGE)
    assert app.running() is True
    assert app.pid > 0
    old_pid = app.pid
    
    app.restart()
    assert old_pid != app.pid
    
    with app:
        app(text="Addition").info
    