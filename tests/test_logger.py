#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Thu Apr 04 2024 16:57:34 by codeskyblue
"""

import logging
import pytest
from uiautomator2 import enable_pretty_logging


def test_enable_pretty_logging(caplog: pytest.LogCaptureFixture):
    logger = logging.getLogger("uiautomator2")
    
    logger.info("should not be printed")
    enable_pretty_logging()
    logger.info("hello")
    enable_pretty_logging(logging.INFO)
    logger.info("world")
    logger.debug("should not be printed")

    # Use caplog.text to check the entire log output as a single string
    assert "hello" in caplog.text
    assert "world" in caplog.text
    assert "should not be printed" not in caplog.text