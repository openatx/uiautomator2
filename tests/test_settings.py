# coding: utf-8
#

import pytest
import logging


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