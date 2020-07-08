# coding: utf-8
#

import threading
from functools import partial
from pprint import pprint

import uiautomator2 as u2
import pytest


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
    #assert not d.xpath("Voice Recognition").exists
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

    elements = sess.xpath('//*[@resource-id="android:id/list"]/android.widget.TextView').all()
    assert len(elements) == 11
    el = elements[0]
    assert el.text == 'Accessibility'


def test_watcher(sess: u2.Session, request):
    sess.xpath.when("App").click()
    sess.xpath.watch_background(interval=1.0)

    event = threading.Event()
    def _set_event(e):
        e.set()

    sess.xpath.when("Action Bar").call(partial(_set_event, event))
    assert event.wait(5.0), "xpath not trigger callback"


@pytest.mark.skip("Deprecated")
def test_watcher_from_yaml(sess: u2.Session, request):
    yaml_content = """---
- when: App
  then: click
- when: Action Bar
  then: >
    def callback(d):
        print("D:", d)
        d.xpath("Alarm").click()
    
    def hello():
        print("World")
"""
    sess.xpath.apply_watch_from_yaml(yaml_content)
    sess.xpath.watch_background(interval=1.0)

    assert sess.xpath("Alarm Controller").wait(timeout=10)


def test_xpath_scroll_to(sess: u2.Session):
    d = sess
    d.xpath("Graphics").click()
    d.xpath("@android:id/list").scroll_to("Pictures")
    assert d.xpath("Pictures").exists

def test_xpath_parent(sess: u2.Session):
    d = sess
    info = d.xpath("App").parent("@android:id/list").info
    assert info['resourceId'] == 'android:id/list'