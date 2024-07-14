# coding: utf-8
# author: codeskyblue

from pathlib import Path
import random
import pytest
import uiautomator2 as u2
from PIL import Image


def test_info(d: u2.Device):
    d.info
    d.device_info
    d.wlan_ip
    assert isinstance(d.serial, str)
    
    w, h = d.window_size()
    assert w > 0 and h > 0
    

def test_dump_hierarchy(d: u2.Device):
    assert d.dump_hierarchy().startswith("<?xml")
    assert d.dump_hierarchy(compressed=True, pretty=True).startswith("<?xml")
    

def test_screenshot(d: u2.Device, tmp_path: Path):
    im = d.screenshot()
    assert isinstance(im, Image.Image)
    
    d.screenshot(tmp_path / "screenshot.png")
    assert (tmp_path / "screenshot.png").exists()


def test_settings(d: u2.Device):
    d.implicitly_wait(10)


def test_click(app: u2.Device):
    app.click(1, 1)
    app.long_click(1, 1)
    app.click(0.5, 0.5)
    app.double_click(1, 1)


def test_swipe_drag(app: u2.Device):
    app.swipe(1, 1, 2, 2, steps=20)
    app.swipe(1, 1, 2, 2, duration=.1)
    app.swipe(1, 1, 2, 2)
    with pytest.warns(UserWarning):
        app.swipe(1, 1, 2, 2, 0.1, 20)
    
    app.swipe_points([(1, 1), (2, 2)], duration=0.1)
    app.drag(1, 1, 2, 2, duration=0.1)


@pytest.mark.parametrize("direction", ["up", "down", "left", "right"])
def test_swipe_ext(d: u2.Device, direction: str):
    d.swipe_ext(direction)


def test_swipe_ext_inside_box(app: u2.Device):
    bounds = app.xpath('@android:id/content').get().bounds
    app.swipe_ext("up", box=bounds)


def test_press(d: u2.Device):
    d.press("volume_down")
    # press home keycode
    d.press(3)
    
    d.long_press("volume_down")
    # long volume_down keycode
    d.long_press(25)
    
    d.keyevent("volume_down")


def test_screen(d: u2.Device):
    # d.screen_off()
    d.screen_on()


def test_orientation(d: u2.Device):
    with pytest.raises(ValueError):
        d.orientation = 'unknown'
        
    d.orientation = 'n'
    assert d.orientation == 'natural'
    d.freeze_rotation(True)
    d.freeze_rotation(False)
    

def test_traversed_text(d: u2.Device):
    d.last_traversed_text
    d.clear_traversed_text()


def test_open(d: u2.Device):
    d.open_notification()
    d.open_quick_settings()
    d.open_url("https://www.baidu.com")


def test_toast(app: u2.Device):
    app.clear_toast()
    assert app.last_toast is None
    
    app(text='Toast').click()
    app(text='Show Toast').click()
    app.sleep(.2)
    assert app.last_toast == "Button Clicked!"
    
    app.clear_toast()
    assert app.last_toast is None


def test_clipboard(d: u2.Device):
    d.set_input_ime()
    text = str(random.randint(0, 1000))
    d.clipboard = f'n{text}'
    assert d.clipboard == f'n{text}'


def test_push_pull(d: u2.Device, tmp_path: Path):
    src_file = tmp_path / "test_push.txt"
    src_file.write_text("12345")
    d.push(src_file, "/data/local/tmp/test_push.txt")
    
    dst_file = tmp_path / "test_pull.txt"
    d.pull("/data/local/tmp/test_push.txt", dst_file)
    assert dst_file.read_text() == "12345"