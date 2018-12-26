# coding: utf-8
#
"""
import uiautomator2 as u2
import uiautomator2.ext.ocr as ocr

u2.plugin_add("ocr", ocr.OCR)

d = u2.connect()
d.ext_ocr("对战模式").click()
"""

import requests
import time

API = ""


class OCRObjectNotFound(Exception):
    pass


class OCR(object):
    def __init__(self, d):
        """
        Args:
            d: uiautomator2 instance
        """
        self._d = d
        if not API:
            raise EnvironmentError("set API var before using OCR")

    def all(self):
        rawdata = self._d.screenshot(format='raw')
        r = requests.post(API, files={"file": ("tmp.jpg", rawdata)})
        r.raise_for_status()
        resp = r.json()
        assert resp['success']
        result = []
        for item in resp['data']:
            lx, ly, rx, ry = item['coords']
            x, y = (lx + rx) // 2, (ly + ry) // 2
            ocr_text = item['text']
            result.append((ocr_text, x, y))
        result.sort(key=lambda v: (v[2], v[1]))
        return result

    def __call__(self, text):
        return OCRSelector(self, text)


class OCRSelector(object):
    def __init__(self, server, text=None, textContains=None):
        self._server = server
        self._d = server._d
        self._text = text
        self._text_contains = textContains

    def all(self):
        result = []
        for (ocr_text, x, y) in self._server.all():
            matched = False
            if self._text == ocr_text:  # exactly match
                matched = True
            elif self._text_contains and self._text_contains in ocr_text:
                matched = True
            if matched:
                result.append((ocr_text, x, y))
        return result

    def wait(self, timeout=10):
        """
        Args:
            timeout: seconds to wait
        
        Returns:
            List of recognition (text, x, y)
            
        Raises:
            OCRObjectNotFound
        """
        deadline = time.time() + timeout
        first = True
        while first or time.time() < deadline:
            first = False
            all = self.all()
            if all:
                return all
        raise OCRObjectNotFound(self._text)

    def click(self, timeout=10):
        result = self.wait(timeout=timeout)
        _, x, y = result[0]
        self._d.click(x, y)


if __name__ == '__main__':
    import uiautomator2.ext.ocr as ocr
    import uiautomator2 as u2

    d = u2.connect()
    print(ocr.OCR(d)("王者峡谷").click())