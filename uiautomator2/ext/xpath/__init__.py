# coding: utf-8
#

import re
import time

from six.moves import shlex_quote
import uiautomator2
from logzero import logger
from lxml import etree
from uiautomator2 import U, E


def safe_xmlstr(s):
    return s.replace("$", "-")


def init():
    uiautomator2.plugin_register("xpath", XPath)


def string_quote(s):
    """ TODO(ssx): quick way to quote string """
    return '"' + s + '"'


class TimeoutException(Exception):
    pass


class XPath(object):
    def __init__(self, d):
        """
        Args:
            d (uiautomator2 instance)
        """
        self._d = d
        self._watchers = []  # item: {"xpath": .., "callback": func}
        self._timeout = 10.0

    def implicitly_wait(self, timeout):
        """ set default timeout when click """
        self._timeout = timeout

    def match(self, xpath, source=None):
        return len(self(xpath, source).all()) > 0

    def when(self, xpath):
        obj = self

        def _click(selector):
            selector.click_nowait()

        class _Watcher():
            def click(self):
                obj._watchers.append({
                    "xpath": xpath,
                    "callback": _click,
                })

            def call(self, func):
                """
                Args:
                    func: accept only one argument "selector"
                """
                obj._watchers.append({
                    "xpath": xpath,
                    "callback": func,
                })

        return _Watcher()

    def run_watchers(self, source=None):
        source = source or self._d.dump_hierarchy()
        for h in self._watchers:
            selector = self(h['xpath'], source)
            if selector.exists:
                logger.info("XPath(hook) %s", h['xpath'])
                h['callback'](selector)
                return True
        return False

    def sleep_watch(self, seconds):
        """ run watchers when sleep """
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.run_watchers()
            left_time = max(0, deadline - time.time())
            time.sleep(min(0.5, left_time))

    def click(self, xpath, source=None, watch=True, timeout=None):
        timeout = timeout or self._timeout
        logger.info("XPath(timeout %.1f) %s", timeout, xpath)

        deadline = time.time() + timeout
        while time.time() < deadline:
            source = self._d.dump_hierarchy()
            if watch and self.run_watchers(source):
                time.sleep(.5)  # post delay
                continue

            selector = self(xpath, source)
            if selector.exists:
                selector.click_nowait()
                time.sleep(.5)  # post sleep
                return
            time.sleep(.5)
            # source = self._d.dump_hierarchy()
        raise TimeoutException("timeout %.1f" % timeout)

    def __call__(self, xpath, source=None):
        if xpath.startswith('//'):
            pass
        elif xpath.startswith('@'):
            xpath = '//*[@resource-id={}]'.format(string_quote(xpath[1:]))
        elif xpath.startswith('^'):
            xpath = '//*[re:match(text(), {})]'.format(string_quote(xpath))
        elif xpath.startswith('%') and xpath.endswith("%"):
            xpath = '//*[contains(text(), {}]'.format(string_quote(xpath))
        elif xpath.startswith('%'):
            xpath = '//*[starts-with(text(), {}]'.format(string_quote(xpath))
        elif xpath.endswith('%'):
            xpath = '//*[ends-with(text(), {}]'.format(string_quote(xpath))
        else:
            xpath = '//*[@text={0} or @content-desc={0}]'.format(
                string_quote(xpath))
        return XPathSelector(self, xpath, source)


class XPathSelector(object):
    def __init__(self, parent, xpath, source=None):
        self._parent = parent
        self._d = parent._d
        self._xpath = xpath
        self._source = source
        self._watchers = []

    def all(self):
        """
        Returns:
            list of XMLElement
        """
        xml_content = self._source or self._d.dump_hierarchy()
        root = etree.fromstring(xml_content.encode('utf-8'))
        for node in root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class"))
        match_nodes = root.xpath(
            U(self._xpath),
            namespaces={"re": "http://exslt.org/regular-expressions"})
        return [XMLElement(node) for node in match_nodes]

    @property
    def exists(self):
        return len(self.all()) > 0

    def click_nowait(self):
        x, y = self.all()[0].center()
        logger.info("click %d, %d", x, y)
        self._d.click(x, y)

    def click(self, timeout=None):
        self._parent.click(self._xpath, timeout=timeout)


class XMLElement(object):
    def __init__(self, elem):
        self.elem = elem

    def center(self):
        bounds = self.elem.attrib.get("bounds")
        lx, ly, rx, ry = map(int, re.findall(r"\d+", bounds))
        return (lx + rx) // 2, (ly + ry) // 2

    @property
    def text(self):
        return self.elem.attrib.get("text")

    @property
    def attrib(self):
        return self.elem.attrib


if __name__ == "__main__":
    init()
    import uiautomator2.ext.htmlreport as htmlreport

    d = uiautomator2.connect()
    hrp = htmlreport.HTMLReport(d)

    # take screenshot before each click
    hrp.patch_click()
    d.app_start("com.netease.cloudmusic", stop=True)

    # watchers
    d.ext_xpath.when("跳过").click()
    # d.ext_xpath.when("知道了").click()

    # steps
    d.ext_xpath("//*[@text='私人FM']/../android.widget.ImageView").click()
    d.ext_xpath("下一首").click()
    d.ext_xpath.sleep_watch(2)
    d.ext_xpath("转到上一层级").click()
