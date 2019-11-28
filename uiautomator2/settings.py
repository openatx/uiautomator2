# coding: utf-8
#

from typing import Any
import uiautomator2 as u2


class Settings(object):
    def __init__(self, d: u2.Device = None):
        self._d = d
        self._defaults = {
            "post_delay": 0,
            "implicitly_wait": 20.0,
        }
        self._props = {
            "post_delay": [float, int],
            "implicitly_wait": [float, int],
        }
        for k, v in self._defaults.items():
            if k not in self._props:
                self._props[k] = type(v)

    def get(self, key: str) -> Any:
        return self._defaults.get(key)
        
    def set(self, key: str, val: Any):
        if key not in self._props:
            raise AttributeError("invalid attribute", key)
        if not isinstance(val, self._props[key]):
            raise TypeError("invalid type, only accept: %s" % self._props[key])
        self._defaults[key] = val

    def __setitem__(self, key: str, val: Any):
        self.set(key, val)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)



if __name__ == "__main__":
    settings = Settings()
    settings.set("pre_delay", 10)
    print(settings['pre_delay'])
    settings["post_delay"] = 10
