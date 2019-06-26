# coding: utf-8
#

import re
import threading
import time

from logzero import logger
from lxml import etree

import uiautomator2
from uiautomator2.exceptions import XPathElementNotFoundError
from uiautomator2.utils import U


def safe_xmlstr(s):
    return s.replace("$", "-")


def init():
    uiautomator2.plugin_register("xpath", XPath)


def string_quote(s):
    """ TODO(ssx): quick way to quote string """
    return '"' + s + '"'


class TimeoutException(Exception):
    pass


class XPathError(Exception):
    """ basic error for xpath plugin """


class XPath(object):
    def __init__(self, d):
        """
        Args:
            d (uiautomator2 instance)
        """
        self._d = d
        self._watchers = []  # item: {"xpath": .., "callback": func}
        self._timeout = 10.0
        self._click_before_delay = 0.0
        self._click_after_delay = None

        # used for click("#back") and back is the key
        self._alias = {}
        self._alias_strict = False
        self._watch_stop_event = threading.Event()
        self._watch_stopped = threading.Event()

    def global_set(self, key, value):  #dicts):
        valid_keys = {
            "timeout", "alias", "alias_strict", "click_after_delay",
            "click_before_delay"
        }
        if key not in valid_keys:
            raise ValueError("invalid key", key)
        setattr(self, "_" + key, value)

    def implicitly_wait(self, timeout):
        """ set default timeout when click """
        self._timeout = timeout

    def dump_hierarchy(self):
        return self._d.dump_hierarchy()

    def send_click(self, x, y):
        if self._click_before_delay:
            logger.debug("click before delay %.1f seconds",
                         self._click_after_delay)
            time.sleep(self._click_before_delay)

        self._d.click(x, y)

        if self._click_after_delay:
            logger.debug("click after delay %.1f seconds",
                         self._click_after_delay)
            time.sleep(self._click_after_delay)

    def send_swipe(self, sx, sy, tx, ty):
        self._d.swipe(sx, sy, tx, ty)

    def match(self, xpath, source=None):
        return len(self(xpath, source).all()) > 0

    def when(self, xpath: str):
        obj = self

        def _click(selector):
            selector.get_last_match().click()

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
        source = source or self.dump_hierarchy()
        for h in self._watchers:
            selector = self(h['xpath'], source)
            if selector.exists:
                logger.info("XPath(hook) %s", h['xpath'])
                h['callback'](selector)
                return True
        return False

    def _watch_forever(self, interval: float):
        try:
            while not self._watch_stopped.wait(timeout=interval):
                self.run_watchers()
        finally:
            self._watch_stopped.clear()
            self._watch_stop_event.set()

    def watch_background(self, interval: float = 4.0):
        th = threading.Thread(name="xpath_watch",
                              target=self._watch_forever,
                              args=(interval, ))
        th.daemon = True
        th.start()
        return th

    def watch_stop(self):
        """ stop watch background """
        if self._watch_stopped.is_set():
            return
        self._watch_stopped.set()
        self._watch_stop_event.wait(timeout=10)
        self._watch_stop_event.clear()

    def watch_clear(self):
        self._watchers = []

    def sleep_watch(self, seconds):
        """ run watchers when sleep """
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.run_watchers()
            left_time = max(0, deadline - time.time())
            time.sleep(min(0.5, left_time))

    def click(self, xpath, source=None, watch=True, timeout=None):
        """
        Args:
            xpath (str): xpath string
            watch (bool): click popup elements
            timeout (float): pass

        Raises:
            TimeoutException
        """
        timeout = timeout or self._timeout
        logger.info("XPath(timeout %.1f) %s", timeout, xpath)

        deadline = time.time() + timeout
        while True:
            source = self.dump_hierarchy()
            if watch and self.run_watchers(source):
                time.sleep(.5)  # post delay
                deadline = time.time() + timeout
                continue

            selector = self(xpath, source)
            if selector.exists:
                selector.get_last_match().click()
                time.sleep(.5)  # post sleep
                return

            if time.time() > deadline:
                break
            time.sleep(.5)

        raise TimeoutException("timeout %.1f" % timeout)

    def __alias_get(self, key, default=None):
        """
        when alias_strict set, if key not in _alias, XPathError will be raised
        """
        value = self._alias.get(key, default)
        if value is None:
            if self._alias_strict:
                raise XPathError("alias have not found key", key)
            value = key
        return value

    def __call__(self, xpath: str, source=None):
        if xpath.startswith('//'):
            pass
        elif xpath.startswith('@'):
            xpath = '//*[@resource-id={}]'.format(string_quote(xpath[1:]))
        elif xpath.startswith('^'):
            xpath = '//*[re:match(text(), {})]'.format(string_quote(xpath))
        elif xpath.startswith("$"):  # special for objects
            key = xpath[1:]
            return self(self.__alias_get(key), source)
        elif xpath.startswith('%') and xpath.endswith("%"):
            xpath = '//*[contains(@text, {})]'.format(string_quote(
                xpath[1:-1]))
        elif xpath.startswith('%'):
            xpath = '//*[starts-with(@text, {})]'.format(
                string_quote(xpath[1:]))
        elif xpath.endswith('%'):
            # //*[ends-with(@text, "suffix")] only valid in Xpath2.0
            xpath = '//*[ends-with(@text, {})]'.format(string_quote(
                xpath[:-1]))
        else:
            xpath = '//*[@text={0} or @content-desc={0}]'.format(
                string_quote(xpath))
        # print("XPATH:", xpath)
        return XPathSelector(self, xpath, source)


class XPathSelector(object):
    def __init__(self, parent: XPath, xpath: str, source=None):
        self._parent = parent
        self._d = parent._d
        self._xpath = xpath
        self._source = source
        self._last_source = None
        self._watchers = []

    @property
    def _global_timeout(self):
        return self._parent._timeout

    def all(self, source=None):
        """
        Returns:
            list of XMLElement
        """
        xml_content = source or self._source or self._parent.dump_hierarchy()
        self._last_source = xml_content

        root = etree.fromstring(xml_content.encode('utf-8'))
        for node in root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class"))
        match_nodes = root.xpath(
            U(self._xpath),
            namespaces={"re": "http://exslt.org/regular-expressions"})
        return [XMLElement(node, self._parent) for node in match_nodes]

    @property
    def exists(self):
        return len(self.all()) > 0

    def get(self):
        """
        Get first matched element

        Returns:
            XMLElement
        
        Raises:
            XPathElementNotFoundError
        """
        if not self.wait(self._global_timeout):
            raise XPathElementNotFoundError(self._xpath)
        return self.get_last_match()

    def get_last_match(self):
        return self.all(self._last_source)[0]

    def get_text(self):
        """
        get element text
        
        Returns:
            string of node text

        Raises:
            XPathElementNotFoundError
        """
        return self.get().attrib.get("text", "")

    def set_text(self, text: str = ""):
        el = self.get()
        self._d.set_fastinput_ime()
        el.click()  # focus input-area
        self._d.clear_text()
        self._d.send_keys(text)

    def wait(self, timeout=None):
        """
        Args:
            timeout (float): seconds

        Raises:
            None or XMLElement
        """
        deadline = time.time() + (timeout or self._global_timeout)
        while time.time() < deadline:
            if self.exists:
                return self.get_last_match()
            time.sleep(.2)
        return None

    def click_nowait(self):
        x, y = self.all()[0].center()
        logger.info("click %d, %d", x, y)
        self._parent.send_click(x, y)

    def click(self, watch=True, timeout=None):
        """
        Args:
            watch (bool): click popup element before real operation
            timeout (float): max wait timeout
        """
        self._parent.click(self._xpath, watch=watch, timeout=timeout)


class XMLElement(object):
    def __init__(self, elem, parent: XPath):
        """
        Args:
            elem: lxml node
            d: uiautomator2 instance
        """
        self.elem = elem
        self._parent = parent

    def center(self):
        """
        Returns:
            (x, y)
        """
        return self.offset(0.5, 0.5)

    def offset(self, px: float = 0.0, py: float = 0.0):
        """
        Offset from left_top

        Args:
            px (float): percent of width
            py (float): percent of height
        
        Example:
            offset(0.5, 0.5) means center
        """
        x, y, width, height = self.rect
        return x + int(width * px), y + int(height * py)

    def click(self):
        """
        click element
        """
        x, y = self.center()
        self._parent.send_click(x, y)

    @property
    def rect(self):
        """
        Returns:
            (left_top_x, left_top_y, width, height)
        """
        bounds = self.elem.attrib.get("bounds")
        lx, ly, rx, ry = map(int, re.findall(r"\d+", bounds))
        return lx, ly, rx - lx, ry - ly

    @property
    def text(self):
        return self.elem.attrib.get("text")

    @property
    def attrib(self):
        return self.elem.attrib


# class Exists(object):
#     """Exists object with magic methods."""

#     def __init__(self, selector):
#         self.selector = selector

#     def __nonzero__(self):
#         """Magic method for bool(self) python2 """
#         return len(self.selector.all()) > 0

#     def __bool__(self):
#         """ Magic method for bool(self) python3 """
#         return self.__nonzero__()

#     def __call__(self, timeout=0):
#         """Magic method for self(args).

#         Args:
#             timeout (float): exists in seconds
#         """
#         if timeout:
#             return self.uiobject.wait(timeout=timeout)
#         return bool(self)

#     def __repr__(self):
#         return str(bool(self))

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
