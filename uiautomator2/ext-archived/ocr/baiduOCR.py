#!/usr/bin/env python3

"""
@version: 1.0.0
@author: rainy008
@description: 使用百度OCR实现截屏选取元素
"""

from aip import AipOcr

from uiautomator2.ext.ocr import OCR as u2OCR
from uiautomator2.ext.ocr import OCRSelector as u2OCRSelector


class OCR(u2OCR):
    def __init__(self, d, app_id, api_key, secrect_key):
        self._d = d
        self._APP_ID = app_id
        self._API_KEY = api_key
        self._SECRECT_KEY = secrect_key
        self._client = AipOcr(self._APP_ID, self._API_KEY, self._SECRECT_KEY)

    def all(self):
        img = self._d.screenshot(format='raw')
        resp = self._client.general(img)  # 通用文字识别(含位置信息版)，每天 500 次免费
        result = []
        for item in resp['words_result']:
            left = item['location'].get('left')
            top = item['location'].get('top')
            width = item['location'].get('width')
            height = item['location'].get('height')
            x, y = left + width // 2, top + height // 2
            ocr_text = item['words']
            result.append((ocr_text, x, y))
        result.sort(key=lambda v: (v[2], v[1]))
        # print(result)
        return result

    def __call__(self, text, exact=True):
        return OCRSelector(self, text, exact)


class OCRSelector(u2OCRSelector):
    def __init__(self, server, text, exact=True):
        self._server = server
        self._d = server._d
        self._text = text
        self._exact = exact

    def all(self):
        result = []
        for (ocr_text, x, y) in self._server.all():
            if self._exact and self._text == ocr_text:  # exactly match
                result.append((ocr_text, x, y))
            elif self._text in ocr_text:
                result.append((ocr_text, x, y))
        return result

    def get_text(self, timeout=10):
        result = self.wait(timeout=timeout)
        word = result[0][0]
        return word


class OCRCustom(OCR):
    def __init__(self, d, app_id, api_key, secrect_key, options):
        super(OCRCustom, self).__init__(d, app_id, api_key, secrect_key)
        self.options = options

    def get_words(self):
        img = self._d.screenshot(format='raw')
        resp = self._client.custom(img, self.options)  # iocr财会票据文字识别(含位置信息版)，每天 500 次免费
        return resp

    def all(self):
        resp = self.get_words()
        result = []
        for item in resp['data']['ret']:
            left = item['location'].get('left')
            top = item['location'].get('top')
            width = item['location'].get('width')
            height = item['location'].get('height')
            x, y = left + width // 2, top + height // 2
            ocr_text = item['word']
            ocr_text_name = item['word_name']
            result.append((ocr_text, x, y))
            result.append((ocr_text_name, x, y))
        result.sort(key=lambda v: (v[2], v[1]))
        # print(result)
        return result

    def get(self, option):
        """
        返回自定义字段的值
        :param option: 自定义的字段，现仅有score和name
        :return:
        """
        resp = self.get_words()
        for item in resp['data']['ret']:
            if item['word_name'] == option:
                return item['word']

