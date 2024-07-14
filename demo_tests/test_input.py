# coding: utf-8
# author: codeskyblue

import pytest
import uiautomator2 as u2


def test_set_ime(d: u2.Device):
    d.set_input_ime(True)
    d.set_input_ime(False)


def test_send_keys(app: u2.Device):
    app(text="Addition").click()
    num1 = app(className="android.widget.EditText", instance=0)
    num2 = app(className="android.widget.EditText", instance=1)
    result = app(className="android.widget.EditText", instance=2)
    
    num1.set_text("5")
    assert num1.get_text() == "5"
    num1.clear_text()
    assert num1.get_text() == ''
    num1.set_text('1')
    
    num2.click()
    app.send_keys('6')
    assert num2.get_text() == '6'
    app.clear_text()
    app.send_keys('2')
    
    app(text="Add").click()
    result = app(className="android.widget.EditText", instance=2).get_text()
    assert result == "3"


def test_send_action(): # TODO
    pass