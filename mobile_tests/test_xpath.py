# coding: utf-8
#

import threading
from functools import partial

import pytest
import uiautomator2 as u2


def test_xpath_selector(sess: u2.Session):
    sel1 = sess.xpath("/a")
    print(str(sel1), type(str(sel1)))
    assert str(sel1).endswith("=/a")
    assert str(sel1.child("/b")).endswith("=/a/b")
    assert str(sel1).endswith("=/a") # sel1 should not be changed
    assert str(sel1.xpath("/b")).endswith("=/a|/b")
    assert str(sel1.xpath(["/b", "/c"])).endswith("=/a|/b|/c")
    assert sel1.position(0.1, 0.1) != sel1
    assert sel1.fallback("click") != sel1
    with pytest.raises(ValueError):
        sel1.fallback("invalid-action")
    

def test_get_text(sess: u2.Session):
    assert sess.xpath("App").get_text() == "App"


def test_click(sess: u2.Session):
    sess.xpath("App").click()
    assert sess.xpath("Alarm").wait()
    assert sess.xpath("Alarm").exists


def test_swipe(sess: u2.Session):
    d = sess
    d.xpath("App").click()
    d.xpath("Alarm").wait()
    # assert not d.xpath("Voice Recognition").exists
    d.xpath("@android:id/list").get().swipe("up", 0.5)
    assert d.xpath("Voice Recognition").wait()


def test_xpath_query(sess: u2.Session):
    assert sess.xpath("Accessibility").wait()
    assert sess.xpath("%ccessibility").wait()
    assert sess.xpath("Accessibilit%").wait()


def test_element_all(sess: u2.Session):
    app = sess.xpath('//*[@text="App"]')
    assert app.wait()
    assert len(app.all()) == 1
    assert app.exists


def test_watcher(sess: u2.Session, request):
    sess.xpath.when("App").click()
    sess.xpath.watch_background(interval=1.0)

    event = threading.Event()

    def _set_event(e):
        e.set()

    sess.xpath.when("Action Bar").call(partial(_set_event, event))
    assert event.wait(5.0), "xpath not trigger callback"


def test_xpath_scroll_to(sess: u2.Session):
    d = sess
    d.xpath("Graphics").click()
    d.xpath("@android:id/list").scroll_to("Pictures")
    assert d.xpath("Pictures").exists


def test_xpath_parent(sess: u2.Session):
    d = sess
    info = d.xpath("App").parent("@android:id/list").info
    assert info["resourceId"] == "android:id/list"
