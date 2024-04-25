#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Thu Apr 25 2024 15:08:43 by codeskyblue
"""

import abc
from typing import Any, List, NamedTuple, Union
import adbutils



class ShellResponse(NamedTuple):
    output: str
    exit_code: int
    
    

class AbstractUiautomatorServer(abc.ABC):
    @abc.abstractmethod
    def start_uiautomator(self):
        pass

    @abc.abstractmethod
    def stop_uiautomator(self):
        pass

    @abc.abstractmethod
    def jsonrpc_call(self, method: str, params: Any = None) -> Any:
        pass



class AbstractShell(abc.ABC):
    @abc.abstractmethod
    def shell(self, cmdargs: Union[List[str], str]) -> ShellResponse:
        pass

    @property
    @abc.abstractmethod
    def adb_device(self) -> adbutils.AdbDevice:
        pass

class AbstractXPathBasedDevice(metaclass=abc.ABCMeta):
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
