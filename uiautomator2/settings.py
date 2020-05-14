# coding: utf-8
#

import json
import logging
import pprint
from typing import Any


logger = logging.getLogger("uiautomator2")

class Settings(object):
    def __init__(self, d):
        self._d = d

        self._defaults = {
            "wait_timeout": 20.0,
            "xpath_debug": False,
            "operation_delay": (0, 0),
            "operation_delay_methods": ["click", "swipe"],
        }

        self._deprecated_props = {
            "click_after_delay": "Use operation_delay instead",
            "click_before_delay": "Use operation_delay instead",
            "post_delay": None,
            "uiautomator_runtest_app_background": None,
        }

        self._props = {
            "post_delay": (float, int),
            "xpath_debug": bool,
        }
        for k, v in self._defaults.items():
            if k not in self._props:
                self._props[k] = (float, int) if type(v) in (float, int) else type(v)
        
        self._set_methods = {
            "operation_delay": self.__set_operation_delay, 
        }

        # self._get_methods = {
        #     "operation_delay": self.__get_operation_delay,
        # }
    
    def __set_operation_delay(self, value: tuple):
        """ 设置操作的(点击)的前后延时 """
        if isinstance(value, (int, float)):
            value = (value, value)
            
        if isinstance(value, (list, tuple)):
            assert len(value) == 2, "operation_delay only accept list with two items"
        _pre, post = value
        assert isinstance(_pre, (int, float)), "operation_delay can only contains int or float"
        assert isinstance(post, (int, float)), "operation_delay can only contains int or float"

        self._defaults["operation_delay"] = (_pre, post)

    def get(self, key: str) -> Any:
        return self._defaults.get(key)
        
    def _set(self, key: str, val: Any):
        # call from methods
        if key in self._set_methods:
            return self._set_methods[key](val)

        # Deprecated properties
        if key in self._deprecated_props:
            reason = self._deprecated_props[key]
            if not reason:
                reason = "{} is deprecated".format(key)
            logger.warning("d.settings[{}] deprecated: {}".format(key, reason))
            return
        
        # Invalid properties
        if key not in self._props:
            raise AttributeError("invalid attribute", key)

        # Type check
        if not isinstance(val, self._props[key]):
            raise TypeError("invalid type, only accept: %r" % self._props[key])

        self._defaults[key] = val

    def __setitem__(self, key: str, val: Any):
        self._set(key, val)

    def __getitem__(self, key: str) -> Any:
        if key not in self._defaults:
            raise RuntimeError("invalid key", key)
        return self.get(key)
    
    def __repr__(self):
        return pprint.pformat(self._defaults)
        # return self._defaults


# if __name__ == "__main__":
#     settings = Settings(None)
#     settings.set("pre_delay", 10)
#     print(settings['pre_delay'])
#     settings["post_delay"] = 10
