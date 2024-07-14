# coding: utf-8
# author: codeskyblue

import pytest
from uiautomator2 import Settings


def test_settings():
    settings = Settings(None)
    settings['wait_timeout'] = 10
    assert settings['wait_timeout'] == 10
    
    with pytest.raises(TypeError):
        settings['wait_timeout'] = '30'
    assert settings['wait_timeout'] == 10
    
    with pytest.raises(AttributeError):
        settings['not_exists_key'] = 1