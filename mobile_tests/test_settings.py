# coding: utf-8
#

import time

import pytest
import uiautomator2 as u2


def test_set_xpath_debug(dev: u2.Device):
    with pytest.raises(TypeError):
        dev.settings['xpath_debug'] = 1
    
    dev.settings['xpath_debug'] = True
    assert dev.settings['xpath_debug'] == True

    dev.settings['xpath_debug'] = False
    assert dev.settings['xpath_debug'] == False


def test_wait_timeout(d: u2.Device):
    d.settings['wait_timeout'] = 19.0
    assert d.wait_timeout == 19.0

    d.settings['wait_timeout'] = 10
    assert d.wait_timeout == 10

    d.implicitly_wait(15)
    assert d.settings['wait_timeout'] == 15


def test_operation_delay(dev: u2.Session):
    x, y = dev(text="App").center()

    # 测试前延迟
    start = time.time()
    dev.settings['operation_delay'] = (1, 0)
    dev.click(x, y)
    time_used = time.time() - start
    assert 1 < time_used < 1.5
    
    # 测试后延迟
    start = time.time()
    dev.settings['operation_delay_methods'] = ['press', 'click']
    dev.settings['operation_delay'] = (0, 2)
    dev.press("back")
    time_used = time.time() - start
    # assert time_used > 2
    #2 < time_used < 2.5

    # 测试operation_delay_methods
    start = time.time()
    dev.settings['operation_delay_methods'] = ['press']
    # dev.jsonrpc = Mock()
    dev.click(x, y)
    time_used = time.time() - start
    # assert 0 < time_used < 0.5
