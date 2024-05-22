# coding: utf-8
#

import threading
from functools import partial

import pytest
import uiautomator2 as u2


def test_get_text(dev: u2.Device):
    assert dev.xpath("App").get_text() == "App"


def test_click(dev: u2.Device):
    dev.xpath("App").click()
    assert dev.xpath("Alarm").wait()
    assert dev.xpath("Alarm").exists


def test_swipe(dev: u2.Device):
    d = dev
    d.xpath("App").click()
    d.xpath("Alarm").wait()
    # assert not d.xpath("Voice Recognition").exists
    d.xpath("@android:id/list").get().swipe("up", 0.5)
    assert d.xpath("Voice Recognition").wait()


def test_xpath_query(dev: u2.Device):
    assert dev.xpath("Accessibility").wait()
    assert dev.xpath("%ccessibility").wait()
    assert dev.xpath("Accessibilit%").wait()


def test_element_all(dev: u2.Device):
    app = dev.xpath('//*[@text="App"]')
    assert app.wait()
    assert len(app.all()) == 1
    assert app.exists


def test_watcher(dev: u2.Device, request):
    dev.watcher.when("App").click()
    dev.watcher.start(interval=1.0)

    event = threading.Event()

    def _set_event(e):
        e.set()

    dev.watcher.when("Action Bar").call(partial(_set_event, event))
    assert event.wait(5.0), "xpath not trigger callback"


def test_xpath_scroll_to(dev: u2.Device):
    d = dev
    d.xpath("Graphics").click()
    d.xpath("@android:id/list").scroll_to("Pictures")
    assert d.xpath("Pictures").exists


def test_xpath_parent(dev: u2.Device):
    d = dev
    info = d.xpath("App").parent("@android:id/list").info
    assert info["resourceId"] == "android:id/list"
