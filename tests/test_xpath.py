# coding: utf-8
#

import uiautomator2 as u2
import pytest

# def setup_function():


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