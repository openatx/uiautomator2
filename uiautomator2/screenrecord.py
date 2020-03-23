# coding: utf-8
#

import uiautomator2 as u2


class Screenrecord:
    def __init__(self, d: u2.Device):
        self._d = d
    
    def __call__(self, filename: str):
        print(filename)
        return self
    
    def stop(self):
        pass

