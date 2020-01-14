# coding: utf-8
#

import json
import logging
import pprint
from typing import Any


class Settings(object):
    def __init__(self, d):
        self._d = d

        self._defaults = {
            "post_delay": 0, # Deprecated
            "wait_timeout": 20.0,
            "xpath_debug": False, #self._set_xpath_debug,
            "uiautomator_runtest_app_background": True,
            "click_after_delay": 0.0,
            "click_before_delay": 0.5,
        }
        self._props = {
            "post_delay": (float, int),
            "xpath_debug": bool,
        }
        for k, v in self._defaults.items():
            if k not in self._props:
                self._props[k] = (float, int) if type(v) in (float, int) else type(v)

    def get(self, key: str) -> Any:
        return self._defaults.get(key)
        
    def set(self, key: str, val: Any):
        if key not in self._props:
            raise AttributeError("invalid attribute", key)
        if not isinstance(val, self._props[key]):
            print(key, self._props[key])
            raise TypeError("invalid type, only accept: %r" % self._props[key])

        # function call
        callback = self._defaults[key]
        if callable(callback):
            callback(val)

        self._defaults[key] = val

    def __setitem__(self, key: str, val: Any):
        self.set(key, val)

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
