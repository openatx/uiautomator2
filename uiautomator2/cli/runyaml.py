#!/usr/bin/env python
# coding: utf-8
#
"""
packageName: com.netease.cloudmusic  # Optional
activity: .MainActivity # Optional
launch: true # Optional, default true
close: true # Optional, close app when finished
plugins:
  ocr: $ocr-api-url
  perf:
    interval: 1
    debug: true
    filename: perf.csv
steps:
- q: ~hell
- q: ^hello w
- q: =hello world
- q: hello world
- q: foo
  timeout: 10 # seconds
- text: the input text
- code: |
    time.sleep(10) # only "d, time" can be used
watchers: # click when show up
- q: ~跳过
  timeout: 0 # default
"""

import argparse
import time
import re
import logging

import uiautomator2 as u2
import logzero
from logzero import logger


class JSONRunner(object):
    __alias = {
        'q': 'query',
    }

    def __init__(self, cnf):
        self._cnf = cnf
        self._title = cnf.get('title')
        self._pkg_name = cnf.get('packageName')
        self._activity = cnf.get('activity')
        self._launch = cnf.get('launch', True)
        self._close = cnf.get('close', True)
        self._clear = cnf.get('clear')
        self._steps = cnf.get('steps')
        self._watchers = cnf.get('watchers', [])
        self._udid = cnf.get('udid')
        self._plugins = cnf.get('plugins', {})
        d = self._d = u2.connect(self._udid)

        self.session = None

        # plugins
        if 'ocr' in self._plugins:
            logger.info("load plugin: ocr")
            import uiautomator2.ext.ocr as ocr
            ocr.API = self._plugins['ocr']
            logger.info("Use ocr plugin: %s", ocr.API)
            u2.plugin_register('ocr', ocr.OCR)
        if self._pkg_name and 'perf' in self._plugins:
            logger.info("load plugin: perf")
            import uiautomator2.ext.perf as perf
            u2.plugin_register('perf', perf.Perf, self._pkg_name)
            perfcnf = self._plugins['perf']
            d.ext_perf.interval = perfcnf.get('interval', 1.0)
            d.ext_perf.debug = perfcnf.get('debug', True)
            d.ext_perf.csv_output = perfcnf.get('filename', 'perf.csv')

    def _find_xpath(self, xpath, hierarchy):
        el = self.session.xpath(xpath, hierarchy)
        if el.exists:
            return el.wait().center()

    def _find_text(self, text, hierarchy):
        elements = self.session.xpath(
            '//*[re:match(name(), "\.(TextView|Button|ImageView)$")]',
            hierarchy).all()
        if text.startswith('~') or text.startswith('^'):  # Regexp
            pattern = re.compile(text[1:] if text.startswith('~') else text)
            for el in elements:
                if el.text and pattern.match(el.text):
                    logger.debug("find match: %s, %s", el.text, el.attrib)
                    return el.center()
        elif text.startswith("="):
            text = text[1:]

        for el in elements:
            if el.text == text:
                logger.debug("find exactly match text: %s", el.text)
                return el.center()

    def _oper_input(self, text):
        logger.info("input text: %s", text)
        self.session.set_fastinput_ime(True)
        self.session.send_keys(text)
        self.session.press("enter")

    def _run_watchers(self, hierarchy):
        for kwargs in self._watchers:
            kwargs['timeout'] = kwargs.get('timeout', 0)
            if 'q' in kwargs:
                kwargs['query'] = kwargs.pop('q')
            if self._run_onestep(hierarchy, **kwargs):
                logger.info("trigger watcher: %s", kwargs)

    def _run_onestep(self,
                     hierarchy,
                     action='click',
                     query=None,
                     text=None,
                     code=None,
                     ocr=None,
                     timeout=10):
        """
        Returns:
            bool: if step handled
        """
        if text:
            self._oper_input(text)
            return True

        if ocr:
            self._d.ext_ocr(ocr).click(timeout=timeout)
            return True

        # find element and click
        if query:
            pos = None
            if query.startswith("/"):
                pos = self._find_xpath(query, hierarchy)
            else:
                pos = self._find_text(query, hierarchy)

            if pos is None:
                if action == 'assertNotExists':
                    return True
                return False

            if action == 'click':
                logger.info("click: %s", pos)
                self.session.click(*pos)
                return True
            elif action == 'assertExists':
                return True

        if code:
            logger.info("exec: |\n%s", code)
            exec(code, {'d': self.session, 'time': time})
            return True

        # raise NotImplementedError("only support click action")

    def _handle_step(self, **kwargs):
        retry_cnt = 0
        timeout = kwargs.pop('timeout', 10)
        deadline = time.time() + timeout

        # alias
        if 'q' in kwargs:
            kwargs['query'] = kwargs.pop('q')

        while retry_cnt == 0 or time.time() < deadline:
            retry_cnt += 1
            hierarchy = self.session.dump_hierarchy()
            self._run_watchers(hierarchy)  # 处理弹框
            if self._run_onestep(hierarchy, **kwargs):
                break
            logger.debug("process %s, retry %d", kwargs, retry_cnt)
            time.sleep(.5)
        else:
            raise RuntimeError("element not found: %s", kwargs)

    def prepare_session(self):
        d = self._d
        if not self._launch or not self._pkg_name:
            self.session = self._d.session(self._pkg_name, attach=True)
            return

        if self._clear:
            d.app_clear(self._pkg_name)

        s = None
        if self._activity:
            d.app_start(self._pkg_name, self._activity, stop=True)
            s = d.session(self._pkg_name, attach=True)
        else:
            s = d.session(self._pkg_name)

        self.session = s

    def run(self):
        logger.info("test begins: %s", self._title)
        logger.info("launch app: %s", self._pkg_name)

        self.prepare_session()

        if 'perf' in self._plugins:
            # add report
            import easyhtmlreport as htmlreport
            hrp = htmlreport.HTMLReport(self._d)
            hrp.patch_click()
            self._d.ext_perf.csv_output = 'report/perf.csv'
            self._d.ext_perf.start()

        try:
            for step in self._steps:
                logger.info("==> %s", step)
                self._handle_step(**step)
            logger.info("Finished")
        finally:
            if 'perf' in self._plugins:
                self._d.ext_perf.stop()
            if self._launch and self._pkg_name and self._close:
                self._d.app_stop(self._pkg_name)


def main(filename, debug=False, onlystep=False):
    if not debug:
        logzero.loglevel(logging.INFO)

    import yaml
    with open(filename, 'rb') as f:
        cnf = yaml.load(f)
        if onlystep:
            cnf['launch'] = False
        tc = JSONRunner(cnf)
        tc.run()


# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument(
#         '-d', '--debug', help='set loglevel to debug', action='store_true')
#     parser.add_argument('--step', help='run only step', action='store_true')
#     parser.add_argument('yamlfile')
#     args = parser.parse_args()

#     main(args.yamlfile, args.debug, onlystep=args.step)
