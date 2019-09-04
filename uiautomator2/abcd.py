# coding: utf-8
# abcd: Abstract Class about Device
#

import abc


class BasicUIMeta(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def click(self, x: int, y: int):
        pass
    
    @abc.abstractmethod
    def swipe(self, fx: int, fy: int, tx: int, ty: int, duration: float):
        """ duration is float type, indicate seconds """
    
    @abc.abstractmethod
    def window_size(self) -> tuple:
        """ return (width, height) """
    
    @abc.abstractmethod
    def dump_hierarchy(self) -> str:
        """ return xml content """
    
    @abc.abstractmethod
    def screenshot(self):
        """ return PIL.Image.Image """
