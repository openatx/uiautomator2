# coding: utf-8
# author: codeskyblue

import time
import pytest
import uiautomator2 as u2
from uiautomator2 import Selector

def test_selector_magic():
    s = Selector(text='123').child(text='456').sibling(text='789').clone()
    assert s['text'] == '123'
    del s['text']
    assert 'text' not in s
    s.update_instance(0)
    

def test_exists(app: u2.Device):
    assert app(text='Addition').exists
    assert app(text='Addition').exists(timeout=.1)
    assert not app(text='should-not-exists').exists
    assert not app(text='should-not-exists').exists(timeout=.1)
    

def test_selector_info(app: u2.Device):
    _info = app(text="Addition").info
    assert _info["text"] == "Addition"
    

@pytest.mark.skip(reason="not stable")
def test_child_by(app: u2.Device):
    app(text="Addition").click()
    app(text='Add').wait()
    time.sleep(.5)
    # childByText, childByInstance and childByDescription run query when called
    app(resourceId='android:id/content').child_by_text("Add")
    app(resourceId='android:id/content').child_by_instance(0)
    with pytest.raises(u2.UiObjectNotFoundError):
        app(resourceId='android:id/content').child_by_description("should-not-exists")
    
    # only run query after call UiObject method
    assert app(resourceId='android:id/content').child_selector(text="Add").exists


def test_screenshot(app: u2.Device):
    lx, ly, rx, ry = app(text="Addition").bounds()
    image = app(text="Addition").screenshot()
    assert image.size == (rx - lx, ry - ly)


def test_center(app: u2.Device):
    x, y = app(text="Addition").center()
    assert x > 0 and y > 0
    

def test_click_exists(app: u2.Device):
    assert app(text="Addition").click_exists()
    app(text='Addition').wait_gone()
    assert not app(text="should-not-exists").click_exists()


@pytest.mark.parametrize("direction", ["up", "down", "left", "right"])
def test_swipe(app: u2.Device, direction: str):
    app(resourceId="android:id/content").swipe(direction)


def test_pinch_gesture(app: u2.Device):
    app(text='Pinch').click()
    app(description='pinch image').wait()
    scale_text = app.xpath('Scale%').get_text()
    assert scale_text.endswith('1.00')
    
    app(description='pinch image').pinch_in(80)
    scale_text = app.xpath('Scale%').get_text()
    assert scale_text.endswith('0.50')
    
    app(description='pinch image').pinch_out()
    scale_text = app.xpath('Scale%').get_text()
    assert scale_text.endswith('3.00')
    
    app().gesture((0.1, 0.5), (0.9, 0.5), (0.5, 0.5), (0.5, 0.5), steps=20)
    scale_text = app.xpath('Scale%').get_text()
    assert scale_text.endswith('0.50')


# TODO
# long_click
# drag_to
# swipe
# guesture