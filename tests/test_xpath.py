#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Thu Apr 04 2024 16:41:25 by codeskyblue
"""

import pytest
from unittest.mock import Mock
from PIL import Image
from uiautomator2.xpath import XMLElement, XPath, XPathSelector, XPathEntry, XPathElementNotFoundError, convert_to_camel_case, is_xpath_syntax_ok, safe_xmlstr, str2bytes, strict_xpath


mock = Mock()
mock.screenshot.return_value = Image.new("RGB", (1080, 1920), "white")
mock.dump_hierarchy.return_value = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="android:id/content" class="FrameLayout" content-desc="" bounds="[0,0][1080,1920]">
    <node index="0" text="n1" resource-id="android:id/text1" class="TextView" content-desc="" bounds="[0,0][1080,100]" />
    <node index="1" text="n2" resource-id="android:id/text2" class="TextView" content-desc="" bounds="[0,100][1080,200]" />
  </node>
  <node index="1" text="" resource-id="android:id/statusBarBackground" class="android.view.View" package="com.android.systemui" content-desc="" bounds="[0,0][1080,24]" />
</hierarchy>
"""

x = XPathEntry(mock)


def test_safe_xmlstr():
    for input, expect in [
        ('android.widget.TextView', 'android.widget.TextView'),
        ('test$123', 'test.123'),
        ('$@#&123.456$', '123.456'),
    ]:
        assert safe_xmlstr(input) == expect


def test_str2bytes():
    assert str2bytes(b'123') == b'123'
    assert str2bytes('123') == b'123'


def test_is_xpath_syntax_ok():
    assert is_xpath_syntax_ok("/a")
    assert is_xpath_syntax_ok("//a")
    assert is_xpath_syntax_ok("//a[@text='b]") is False
    assert is_xpath_syntax_ok("//a[") is False


def test_convert_to_camel_case():
    assert convert_to_camel_case("hello-world") == "helloWorld"


def test_strict_xpath():
    for (input, expect) in [
        ("@n1", "//*[@resource-id='n1']"),
        ("//TextView", "//TextView"),
        ("//TextView[@text='n1']", "//TextView[@text='n1']"),
        ("(//TextView)[2]", "(//TextView)[2]"),
        ("//TextView/", "//TextView"), # test rstrip /
    ]:
        assert strict_xpath(input) == expect


def test_XPath():
    xp = XPath("//TextView")
    assert xp == "//TextView"
    assert xp.joinpath("/n1") == "//TextView/n1"



def test_xpath_selector():
    assert isinstance(x("n1"), XPathSelector)
    assert isinstance(x("//TextView"), XPathSelector)
    xp1 = x("n1")
    xp2 = xp1.child("n2")
    # xp1 should not be changed
    assert xp1.get(timeout=0).text == "n1"
    assert xp1.get_text() == "n1"

    # match return None or XMLElement
    assert xp1.match() is not None
    assert xp2.match() is None


def test_xpath_with_instance():
    # issue: https://github.com/openatx/uiautomator2/issues/941
    el = x('(//TextView)[2]').get(0)
    assert el.text == "n2"


def test_xpath_click():
    x("n1").click()
    assert mock.click.called
    assert mock.click.call_args[0] == (540, 50)

    mock.click.reset_mock()
    assert x("n1").click_exists() == True
    assert mock.click.call_args[0] == (540, 50)
    
    mock.click.reset_mock()
    assert x("n3").click_exists(timeout=.1) == False
    assert not mock.click.called


def test_xpath_exists():
    assert x("n1").exists
    assert not x("n3").exists


def test_xpath_wait_and_wait_gone():
    assert x("n1").wait() is True
    assert x("n3").wait(timeout=.1) is False

    assert x("n3").wait_gone(timeout=.1) is True
    assert x("n1").wait_gone(timeout=.1) is False


def test_xpath_get():
    assert x("n1").get().text == "n1"
    assert x("n2").get().text == "n2"

    with pytest.raises(XPathElementNotFoundError):
        x("n3").get(timeout=.1)


def test_xpath_all():
    assert len(x("//TextView").all()) == 2
    assert len(x("n3").all()) == 0

    assert len(x("n1").all()) == 1
    el = x("n1").all()[0]
    assert isinstance(el, XMLElement)
    assert el.text == "n1"


def test_xpath_element():
    el = x("n1").get(timeout=0)
    assert el.text == "n1"
    assert el.center() == (540, 50)
    assert el.offset(0, 0) == (0, 0)
    assert el.offset(1, 1) == (1080, 100)
    assert el.screenshot().size == (1080, 100)
    assert el.bounds == (0, 0, 1080, 100)
    assert el.rect == (0, 0, 1080, 100)
    assert isinstance(el.info, dict)
    assert el.get_xpath(strip_index=True) == "/hierarchy/FrameLayout/TextView"
    
    mock.click.reset_mock()
    el.click()
    assert mock.click.called
    assert mock.click.call_args[0] == (540, 50)

    mock.long_click.reset_mock()
    el.long_click()
    assert mock.long_click.called
    assert mock.long_click.call_args[0] == (540, 50)

    mock.swipe.reset_mock()
    el.swipe("up")
    assert mock.swipe.called


