#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Wed May 22 2024 16:23:56 by codeskyblue
"""

import base64
from dataclasses import dataclass
import re
from typing import Dict, Optional, Union
import warnings

from retry import retry

from uiautomator2.abstract import AbstractShell
from uiautomator2.exceptions import AdbBroadcastError, DeviceError
from uiautomator2.utils import deprecated


@dataclass
class BroadcastResult:
    code: Optional[int]
    data: Optional[str]


BORADCAST_RESULT_OK = -1
BROADCAST_RESULT_CANCELED = 0



class InputMethodMixIn(AbstractShell):
    @property
    def clipboard(self):
        result = self._broadcast("ADB_KEYBOARD_GET_CLIPBOARD")
        if result.code == BORADCAST_RESULT_OK:
            return base64.b64decode(result.data).decode('utf-8')
        return self.jsonrpc.getClipboard()

    def set_input_ime(self, enable: bool = True):
        """ Enable of Disable InputIME """
        ime_id = 'com.github.uiautomator/.AdbKeyboard'
        if not enable:
            self.shell(['ime', 'disable', ime_id])
            return
        
        if self.current_ime() == ime_id:
            return
        self.shell(['ime', 'enable', ime_id])
        self.shell(['ime', 'set', ime_id])
        self.shell(['settings', 'put', 'secure', 'default_input_method', ime_id])
    
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
        try:
            self.set_input_ime()
            btext = text.encode('utf-8')
            base64text = base64.b64encode(btext).decode()
            cmd = "ADB_KEYBOARD_SET_TEXT" if clear else "ADB_KEYBOARD_INPUT_TEXT"
            self._must_broadcast(cmd, {"text": base64text})
            return True
        except AdbBroadcastError:
            warnings.warn(
                "set FastInputIME failed. use \"d(focused=True).set_text instead\"",
                Warning)
            return self(focused=True).set_text(text)
            # warnings.warn("set FastInputIME failed. use \"adb shell input text\" instead", Warning)
            # self.shell(["input", "text", text.replace(" ", "%s")])

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
    
    @deprecated(reason="use set_input_ime instead")
    def set_fastinput_ime(self, enable: bool = True):
        return self.set_input_ime(enable)
    
    @deprecated(reason="use set_input_ime instead")
    def wait_fastinput_ime(self, timeout=5.0):
        """ wait FastInputIME is ready (Depreacated in version 3.1) """
        pass
