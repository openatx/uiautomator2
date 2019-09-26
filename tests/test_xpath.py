# coding: utf-8
#

import threading
from functools import partial

import uiautomator2 as u2
import pytest


def test_get_text(sess: u2.Session):
    assert sess.xpath("App").get_text() == "App"


def test_click(sess: u2.Session):
    sess.xpath("App").click()
    assert sess.xpath("Alarm").wait()
    assert sess.xpath("Alarm").exists


def test_all(sess: u2.Session):
    app = sess.xpath('//*[@text="App"]')
    assert app.wait()
    assert len(app.all()) == 1
    assert app.exists


def test_watcher(sess: u2.Session, request):
    sess.xpath.when("App").click()
    sess.xpath.watch_background(interval=1.0)
    request.addfinalizer(lambda: sess.xpath.watch_stop() and sess.xpath.watch_clear())

    event = threading.Event()
    def _set_event(e):
        e.set()

    sess.xpath.when("Action Bar").call(partial(_set_event, event))
    assert event.wait(5.0), "xpath not trigger callback"


def test_watcher_from_yaml(sess: u2.Session, request):
    yaml_content = """---
- when: App
  then: click
- when: Action Bar
  then: >
    def callback(d):
        d.xpath("Alarm").click()
"""
    sess.xpath.apply_watch_from_yaml(yaml_content)
    sess.xpath.watch_background(interval=1.0)
    request.addfinalizer(lambda: sess.xpath.watch_stop() and sess.xpath.watch_clear())

    assert sess.xpath("Alarm Controller").wait(timeout=10)
