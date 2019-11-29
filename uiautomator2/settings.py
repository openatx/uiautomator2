# coding: utf-8
#

import pprint
from typing import Any


class Settings(object):
    def __init__(self):
        self._defaults = {
            "post_delay": 0,
            "wait_timeout": 20.0,
        }
        self._props = {
            "post_delay": (float, int),
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
        self._defaults[key] = val

    def __setitem__(self, key: str, val: Any):
        self.set(key, val)

    def __getitem__(self, key: str) -> Any:
        if key not in self._defaults:
            raise RuntimeError("invalid key", key)
        return self.get(key)
    
    def __repr__(self):
        return pprint.pformat(self._defaults)




if __name__ == "__main__":
    settings = Settings()
    settings.set("pre_delay", 10)
    print(settings['pre_delay'])
    settings["post_delay"] = 10
