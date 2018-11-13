# coding: utf-8
#

import re
import time
import uiautomator2
from logzero import logger
from lxml import etree


def safe_xmlstr(s):
    return s.replace("$", "-")


def init():
    uiautomator2.plugin_register("xpath", XPath)


class TimeoutException(Exception):
    pass


class XPath(object):
    def __init__(self, d):
        """
        Args:
            d (uiautomator2 instance)
        """
        self._d = d
        self._handlers = []  # item: {"xpath": .., "callback": func}

    def match(self, xpath, source=None):
        return len(self(xpath, source).all()) > 0

    def when(self, xpath):
        obj = self

        def _click(selector):
            selector.click_nowait()

        class _Watcher():
            def click(self):
                obj._handlers.append({
                    "xpath": xpath,
                    "callback": _click,
                })
            
            def call(self, func):
                """
                Args:
                    func: accept only one argument "selector"
                """
                obj._handlers.append({
                    "xpath": xpath,
                    "callback": func,
                })

        return _Watcher()

    def click(self, xpath, source=None, watch=True, timeout=10.0):
        source = self._d.dump_hierarchy()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if watch:
                for h in self._handlers:
                    selector = self(h['xpath'], source)
                    if selector.exists:
                        logger.info("watch match %s", h['xpath'])
                        h['callback'](selector)
                        time.sleep(.5)
                        break
                else:
                    break
            source = self._d.dump_hierarchy()
            selector = self(xpath, source)
            if selector.exists:
                selector.click_nowait()
                time.sleep(.5)  # post sleep
                return
        raise TimeoutException("timeout %.1f" % timeout)

    def __call__(self, xpath, source=None):
        if xpath.startswith('//'):
            return XPathSelector(self._d, xpath, source)
        if xpath.startswith('@'):
            return XPathSelector(self._d, xpath[1:], source)
        raise RuntimeError("Invalid xpath", xpath)


class XPathSelector(object):
    def __init__(self, d, xpath, source=None):
        self._d = d
        self._xpath = xpath
        self._source = source
        self._handlers = []

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
            self._xpath,
            namespaces={"re": "http://exslt.org/regular-expressions"})
        return [XMLElement(node) for node in match_nodes]

    @property
    def exists(self):
        return self.all() > 0

    def click_nowait(self):
        x, y = self.all()[0].center()
        logger.info("click %d, %d", x, y)
        self._d.click(x, y)


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
    d = uiautomator2.connect()
    d.ext_xpath("//*[@resource-id='smartisanos:id/right_container']").click()