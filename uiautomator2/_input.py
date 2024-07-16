#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Wed May 22 2024 16:23:56 by codeskyblue
"""

import base64
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Union
import warnings

from retry import retry

from uiautomator2.abstract import AbstractShell
from uiautomator2.exceptions import AdbBroadcastError, DeviceError, InputIMEError
from uiautomator2.utils import deprecated


logger = logging.getLogger(__name__)

@dataclass
class BroadcastResult:
    code: Optional[int]
    data: Optional[str]


BORADCAST_RESULT_OK = -1
BROADCAST_RESULT_CANCELED = 0



class InputMethodMixIn(AbstractShell):
    # @property
    # def clipboard(self) -> Optional[str]:
    #     result = self._broadcast("ADB_KEYBOARD_GET_CLIPBOARD")
    #     if result.code == BORADCAST_RESULT_OK:
    #         return base64.b64decode(result.data).decode('utf-8')
    #     # jsonrpc.getClipboard is not OK for now
    #     return None
    
    @property
    def __ime_id(self) -> str:
        return 'com.github.uiautomator/.AdbKeyboard'

    def set_input_ime(self, enable: bool = True):
        """ Enable of Disable InputIME """
        if not enable:
            self.shell(['ime', 'disable', self.__ime_id])
            return
        if self.current_ime() == self.__ime_id:
            return
        # prepare ime
        if self.__ime_id not in self.__get_ime_list():
            self.__setup_ime()
        assert self.__ime_id in self.__get_ime_list()
        
        self.shell(['ime', 'enable', self.__ime_id])
        self.shell(['ime', 'set', self.__ime_id])
        self.shell(['settings', 'put', 'secure', 'default_input_method', self.__ime_id])
    
    def __setup_ime(self):
        logger.debug("installing AdbKeyboard ime")
        assets_dir = Path(__file__).parent / "assets"
        ime_apk_path = assets_dir / 'app-uiautomator.apk'
        self.adb_device.install(str(ime_apk_path), nolaunch=True, uninstall=True)
        # wait for ime registered
        for _ in range(10):
            if self.__ime_id in self.__get_ime_list():
                return
            time.sleep(.3)
        raise InputIMEError("install AdbKeyboard ime failed")
    
    def _broadcast(self, action: str, extras: Dict[str, str] = {}) -> BroadcastResult:
        # requires ATX 2.4.0+
        args = ['am', 'broadcast', '-a', action]
        for k, v in extras.items():
            if isinstance(v, int):
                args.extend(['--ei', k, str(v)])
            else:
                args.extend(['--es', k, v])
        # Example output: result=-1 data="success"
        output = self.shell(args).output
        m_result = re.search(r'result=(-?\d+)', output)
        m_data = re.search(r'data="([^"]+)"', output)
        result = int(m_result.group(1)) if m_result else None
        data = m_data.group(1) if m_data else None
        return BroadcastResult(result, data)
    
    @retry(AdbBroadcastError, tries=3, delay=1, jitter=0.5)
    def _must_broadcast(self, action: str, extras: Dict[str, str] = {}):
        result = self._broadcast(action, extras)
        if result.code != BORADCAST_RESULT_OK:
            raise AdbBroadcastError(f"broadcast {action} failed: {result.data}")

    def send_keys(self, text: str, clear: bool = False):
        """
        Args:
            text (str): text to set
            clear (bool): clear before set text
        """
        if clear:
            self.clear_text()
        if re.match(r'^[-+*\/_a-zA-Z0-9 ]+$', text):
            self.shell(['input', 'text', text.replace(' ', '%s')])
        else:
            self.__send_keys_with_ime(text)

    def __send_keys_with_ime(self, text: str):
        try:
            self.set_input_ime()
            btext = text.encode('utf-8')
            base64text = base64.b64encode(btext).decode()
            cmd = "ADB_KEYBOARD_INPUT_TEXT"
            self._must_broadcast(cmd, {"text": base64text})
            return True
        except AdbBroadcastError:
            warnings.warn(
                "set FastInputIME failed. use \"d(focused=True).set_text instead\"",
                Warning)
            return self(focused=True).set_text(text)
        
    def send_action(self, code: Union[str, int] = None):
        """
        Simulate input method edito code

        Args:
            code (str or int): input method editor code

        Examples:
            send_action("search"), send_action(3)

        Refs:
            https://developer.android.com/reference/android/view/inputmethod/EditorInfo
        """
        self.set_input_ime(True)
        __alias = {
            "go": 2,
            "search": 3,
            "send": 4,
            "next": 5,
            "done": 6,
            "previous": 7,
        }
        if isinstance(code, str):
            code = __alias.get(code, code)
        if code:
            self._must_broadcast('ADB_KEYBOARD_EDITOR_CODE', {"code": str(code)})
        else:
            self._must_broadcast('ADB_KEYBOARD_SMART_ENTER')

    def clear_text(self):
        """ clear text
        Raises:
            EnvironmentError
        """
        try:
            self.set_input_ime(True)
            self._must_broadcast('ADB_KEYBOARD_CLEAR_TEXT')
        except AdbBroadcastError:
            # for Android simulator
            self(focused=True).clear_text()

    def current_ime(self) -> str:
        """ Current input method
        Returns:
            ime_method

        Example output:
            "com.github.uiautomator/.FastInputIME"
        """
        return self.shell(['settings', 'get', 'secure', 'default_input_method']).output.strip()
        # _INPUT_METHOD_RE = re.compile(r'mCurMethodId=([-_./\w]+)')
        # dim, _ = self.shell(['dumpsys', 'input_method'])
        # m = _INPUT_METHOD_RE.search(dim)
        # method_id = None if not m else m.group(1)
        # shown = "mInputShown=true" in dim
        # return (method_id, shown)
    
    def __get_ime_list(self) -> List[str]:
        ret = self.shell(['ime', 'list', '-s', '-a'])
        return ret.output.strip().splitlines(keepends=False)
        
    @deprecated(reason="use set_input_ime instead")
    def set_fastinput_ime(self, enable: bool = True):
        return self.set_input_ime(enable)
    
    @deprecated(reason="use set_input_ime instead")
    def wait_fastinput_ime(self, timeout=5.0):
        """ wait FastInputIME is ready (Depreacated in version 3.1) """
        pass
