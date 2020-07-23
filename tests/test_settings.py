# coding: utf-8
#

import uiautomator2 as u2
import pytest
import logging
import time


def test_set_xpath_debug(sess):
    with pytest.raises(TypeError):
        sess.settings['xpath_debug'] = 1
    
    sess.settings['xpath_debug'] = True
    assert sess.settings['xpath_debug'] == True
    assert sess.xpath.logger.level == logging.DEBUG

    sess.settings['xpath_debug'] = False
    assert sess.settings['xpath_debug'] == False
    assert sess.xpath.logger.level == logging.INFO


def test_wait_timeout(d):
    d.settings['wait_timeout'] = 19.0
    assert d.wait_timeout == 19.0

    d.settings['wait_timeout'] = 10
    assert d.wait_timeout == 10

    d.implicitly_wait(15)
    assert d.settings['wait_timeout'] == 15


def test_operation_delay(d: u2.Device):
    x, y = d(text="App").center()

    # 测试前延迟
    start = time.time()
    d.settings['operation_delay'] = (1, 0)
    d.click(x, y)
    time_used = time.time() - start
    assert 1 < time_used < 1.5
    
    # 测试后延迟
    start = time.time()
    d.settings['operation_delay_methods'] = ['press', 'click']
    d.settings['operation_delay'] = (0, 2)
    d.press("back")
    time_used = time.time() - start
    assert time_used > 2
    #2 < time_used < 2.5

    # 测试operation_delay_methods
    start = time.time()
    d.settings['operation_delay_methods'] = ['press']
    d.click(x, y)
    time_used = time.time() - start
    assert 0 < time_used < .5
