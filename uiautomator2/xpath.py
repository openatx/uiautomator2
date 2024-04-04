# coding: utf-8
#

from __future__ import absolute_import

import functools
import logging
import re
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Union

from deprecated import deprecated
from PIL import Image
from lxml import etree

from uiautomator2._proto import Direction
from uiautomator2.abcd import DeviceInterface
from uiautomator2.exceptions import XPathElementNotFoundError
from uiautomator2.utils import inject_call, swipe_in_bounds


logger = logging.getLogger(__name__)

def safe_xmlstr(s):
    return s.replace("$", "-")


def string_quote(s):
    """quick way to quote string"""
    return "{!r}".format(s)


def str2bytes(v: Union[str, bytes]) -> bytes:
    if isinstance(v, bytes):
        return v
    return v.encode("utf-8")


def is_xpath_syntax_ok(xpath_expression: str) -> bool:
    try:
        etree.XPath(xpath_expression)
        return True  # No error means the XPath syntax is likely okay
    except etree.XPathSyntaxError:
        return False  # Indicates a syntax error in the XPath expression


def strict_xpath(xpath: str) -> str:
    """make xpath to be computer recognized xpath"""
    orig_xpath = xpath

    if xpath.startswith("/"):
        pass
    elif xpath.startswith("@"):
        xpath = "//*[@resource-id={!r}]".format(xpath[1:])
    elif xpath.startswith("^"):
        xpath = "//*[re:match(@text, {0}) or re:match(@content-desc, {0}) or re:match(@resource-id, {0})]".format(
            string_quote(xpath)
        )
    # elif xpath.startswith("$"):  # special for objects
    #     key = xpath[1:]
    #     return self(self.__alias_get(key), source)
    elif xpath.startswith("%") and xpath.endswith("%"):
        xpath = "//*[contains(@text, {0}) or contains(@content-desc, {0})]".format(
            string_quote(xpath[1:-1])
        )
    elif xpath.startswith("%"):  # ends-with
        text = xpath[1:]
        xpath = "//*[{0} = substring(@text, string-length(@text) - {1} + 1) or {0} = substring(@content-desc, string-length(@text) - {1} + 1)]".format(
            string_quote(text), len(text)
        )
    elif xpath.endswith("%"):  # starts-with
        text = xpath[:-1]
        xpath = (
            "//*[starts-with(@text, {0}) or starts-with(@content-desc, {0})]".format(
                string_quote(text)
            )
        )
    else:
        xpath = "//*[@text={0} or @content-desc={0} or @resource-id={0}]".format(
            string_quote(xpath)
        )

    if not is_xpath_syntax_ok(xpath):
        raise XPathError("Invalid xpath", orig_xpath)
    logger.debug("xpath %s -> %s", orig_xpath, xpath)
    return xpath


class TimeoutException(Exception):
    pass


class XPathError(Exception):
    """basic error for xpath plugin"""

class XPath(object):
    def __init__(self, d: DeviceInterface):
        """
        Args:
            d (uiautomator2 instance)
        """
        self._d = d
        assert hasattr(d, "wait_timeout")
        # TODO: remove wait_timeout

        self._click_before_delay = 0.0  # pre delay
        self._click_after_delay = None  # post delay
        self._last_source = None
        self._event_callbacks = defaultdict(list)

        # used for click("#back") and back is the key
        self._alias = {}
        self._alias_strict = False
        self._dump_lock = threading.Lock()

    def global_set(self, key, value):
        valid_keys = {
            "timeout",
            "alias",
            "alias_strict",
            "click_after_delay",
            "click_before_delay",
        }
        if key not in valid_keys:
            raise ValueError("invalid key", key)
        if key == "timeout":
            self.implicitly_wait(value)
        else:
            setattr(self, "_" + key, value)

    def implicitly_wait(self, timeout):
        """set default timeout when click"""
        self._d.wait_timeout = timeout

    @property
    def wait_timeout(self):
        return self._d.wait_timeout

    @property
    def _watcher(self):
        return self._d.watcher

    def dump_hierarchy(self):
        with self._dump_lock:
            self._last_source = self._d.dump_hierarchy()
            return self._last_source

    def get_last_hierarchy(self):
        return self._last_source

    def add_event_listener(self, event_name, callback):
        self._event_callbacks[event_name] += [callback]

    # def register_callback(action: str, callback):
    #     pass

    def send_click(self, x, y):
        if self._click_before_delay:
            logger.debug(
                "click before delay %.1f seconds", self._click_after_delay
            )
            time.sleep(self._click_before_delay)

        # TODO(ssx): should use a better way
        # event callbacks for report generate
        for callback_func in self._event_callbacks["send_click"]:
            callback_func(x, y)

        self._d.click(x, y)

        if self._click_after_delay:
            logger.debug("click after delay %.1f seconds", self._click_after_delay)
            time.sleep(self._click_after_delay)

    def send_longclick(self, x, y):
        self._d.long_click(x, y)

    def send_swipe(self, sx, sy, tx, ty):
        self._d.swipe(sx, sy, tx, ty)

    def send_text(self, text: str = None):
        self._d.set_fastinput_ime()
        self._d.clear_text()
        if text:
            self._d.send_keys(text)

    def take_screenshot(self) -> Image.Image:
        return self._d.screenshot()

    def match(self, xpath, source=None):
        return len(self(xpath, source).all()) > 0

    @deprecated(version="3.0.0", reason="use d.watcher.when(..) instead")
    def when(self, xquery: str):
        return self._watcher.when(xquery)

    @deprecated(version="3.0.0", reason="use d.watcher.run() instead")
    def run_watchers(self, source=None):
        self._watcher.run()

    @deprecated(version="3.0.0", reason="use d.watcher.start(..) instead")
    def watch_background(self, interval: float = 4.0):
        return self._watcher.start(interval)

    @deprecated(version="3.0.0", reason="use d.watcher.stop() instead")
    def watch_stop(self):
        """stop watch background"""
        self._watcher.stop()

    @deprecated(version="3.0.0", reason="use d.watcher.remove() instead")
    def watch_clear(self):
        self._watcher.stop()

    @deprecated(version="3.0.0", reason="removed")
    def sleep_watch(self, seconds):
        """run watchers when sleep"""
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.run_watchers()
            left_time = max(0, deadline - time.time())
            time.sleep(min(0.5, left_time))

    def _get_after_watch(self, xpath: Union[str, list], timeout=None):
        if timeout == 0:
            timeout = 0.01
        timeout = timeout or self.wait_timeout
        logger.info("XPath(timeout %.1f) %s", timeout, xpath)
        deadline = time.time() + timeout
        while True:
            source = self.dump_hierarchy()

            selector = self(xpath, source)
            if selector.exists:
                return selector.get_last_match()

            if time.time() > deadline:
                break
            time.sleep(0.5)

        raise TimeoutException("timeout %.1f, xpath: %s" % (timeout, xpath))

    def click(self, xpath: Union[str, list], timeout=None, pre_delay: float = None):
        """
        Find element and perform click

        Args:
            xpath (str): xpath string
            timeout (float): pass
            pre_delay (float): pre delay wait time before click

        Raises:
            TimeoutException
        """
        el = self._get_after_watch(xpath, timeout)
        el.click()  # 100ms

    def scroll_to(
        self,
        xpath: str,
        direction: Union[Direction, str] = Direction.FORWARD,
        max_swipes=10,
    ) -> Union["XMLElement", None]:
        """
        Need more tests
        scroll up the whole screen until target element founded

        Returns:
            bool (found or not)
        """
        if direction == Direction.FORWARD:
            direction = Direction.UP
        elif direction == Direction.BACKWARD:
            direction = Direction.DOWN
        elif direction == Direction.HORIZ_FORWARD:  # Horizontal
            direction = Direction.LEFT
        elif direction == Direction.HBACKWORD:
            direction = Direction.RIGHT

        # FIXME(ssx): 还差一个检测是否到底的功能
        assert max_swipes > 0
        target = self(xpath)
        for i in range(max_swipes):
            if target.exists:
                self._d.swipe_ext(direction, 0.1)  # 防止元素停留在边缘
                return target.get_last_match()
            self._d.swipe_ext(direction, 0.5)
        return False

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
        return XPathSelector(self, xpath, source)


class XPathSelector(object):
    def __init__(self, parent: XPath, xpath: str = None, source: str = None):
        self._parent = parent
        self._d = parent._d
        self._source = source
        self._last_source = None
        self._position = None
        self._fallback = None
        self._xpath_list = (strict_xpath(xpath),) if xpath else ()

    def __str__(self):
        return f"XPathSelector={'|'.join(self._xpath_list)}"

    def copy(self) -> "XPathSelector":
        """copy self"""
        new = XPathSelector(self._parent)
        new._source = self._source
        new._last_source = self._last_source
        new._position = self._position
        new._fallback = self._fallback
        new._xpath_list = self._xpath_list
        return new

    def xpath(self, _xpath: Union[list, tuple, str]):
        """
        add xpath to condition list
        the element should match all conditions
        """
        new = self.copy()
        if isinstance(_xpath, (list, tuple)):
            for xp in _xpath:
                new = new.xpath(xp)
        else:
            new._xpath_list = new._xpath_list + (strict_xpath(_xpath),)
        return new

    def child(self, _xpath: str) -> "XPathSelector":
        """
        add child xpath
        """
        if not _xpath.startswith("/"):
            _xpath = "/" + _xpath
        new = self.copy()
        new._xpath_list = new._xpath_list[:-1] + (new._xpath_list[-1] + _xpath,)
        return new

    def position(self, x: float, y: float):
        """set possible position"""
        assert 0 < x < 1
        assert 0 < y < 1
        new = self.copy()
        new._position = (x, y)
        return new

    def fallback(self, func: Optional[Callable[..., bool]] = None, *args, **kwargs):
        """
        callback on failure
        """
        if isinstance(func, str):
            if func == "click":
                if len(args) == 0:
                    args = self._position
                func = lambda d: d.click(*args)
            else:
                raise ValueError('func should be "click" or callable function')

        assert callable(func)
        new = self.copy()
        new._fallback = func
        return new

    @property
    def _global_timeout(self) -> float:
        if hasattr(self._parent, "wait_timeout") and isinstance(self._parent.wait_timeout, (int, float)):
            return self._parent.wait_timeout
        return 20.0

    def all(self, source=None) -> List["XMLElement"]:
        """find all matched elements"""
        xml_content = source or self._source or self._parent.dump_hierarchy()
        self._last_source = xml_content

        # run-watchers
        hierarchy = source or self._source
        if not hierarchy:
            trigger_count = 0
            for _ in range(5):  # trigger for most 5 times
                triggered = self._parent._watcher.run(xml_content)
                if not triggered:
                    break
                trigger_count += 1
                xml_content = self._parent.dump_hierarchy()
            if trigger_count:
                logger.debug("watcher triggered %d times", trigger_count)

        if hierarchy is None:
            root = etree.fromstring(str2bytes(xml_content))
        elif isinstance(hierarchy, (str, bytes)):
            root = etree.fromstring(str2bytes(hierarchy))
        elif isinstance(hierarchy, etree._Element):
            root = hierarchy
        else:
            raise TypeError("Unknown type", type(hierarchy))

        for node in root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class", "")) or "node"

        match_sets = []
        for xpath in self._xpath_list:
            matches = root.xpath(
                xpath, namespaces={"re": "http://exslt.org/regular-expressions"}
            )
            match_sets.append(matches)
        # find out nodes which match all xpaths
        match_nodes = functools.reduce(lambda x, y: set(x).intersection(y), match_sets)
        els = [XMLElement(node, self._parent) for node in match_nodes]
        if not self._position:
            return els

        # 中心点应控制在控件内
        inside_els = []
        px, py = self._position
        wsize = self._d.window_size()
        for e in els:
            lpx, lpy, rpx, rpy = e.percent_bounds(wsize=wsize)
            # 中心点偏移百分比不应大于控件宽高的50%
            scale = 1.5

            if abs(px - (lpx + rpx) / 2) > (rpx - lpx) * 0.5 * scale:
                continue
            if abs(py - (lpy + rpy) / 2) > (rpy - lpy) * 0.5 * scale:
                continue
            inside_els.append(e)
        return inside_els

    @property
    def exists(self):
        return len(self.all()) > 0

    def get(self, timeout=None):
        """
        Get first matched element

        Args:
            timeout (float): max seconds to wait

        Returns:
            XMLElement

        Raises:
            XPathElementNotFoundError
        """
        if not self.wait(timeout or self._global_timeout):
            raise XPathElementNotFoundError(self._xpath_list)
        return self.get_last_match()

    def get_last_match(self):
        return self.all(self._last_source)[0]

    def get_text(self) -> Optional[str]:
        """
        get element text

        Returns:
            string of node text

        Raises:
            XPathElementNotFoundError
        """
        return self.get().text

    def set_text(self, text: str = ""):
        el = self.get()
        self._d.set_fastinput_ime()  # switch ime
        el.click()  # focus input-area
        self._parent.send_text(text)

    def wait(self, timeout=None) -> bool:
        """ wait until element found """
        deadline = time.time() + (timeout or self._global_timeout)
        while True:
            if self.exists:
                return True
            if time.time() > deadline:
                return False
            time.sleep(0.2)

    def match(self) -> Optional["XMLElement"]:
        """
        Returns:
            None or matched XMLElement
        """
        if self.exists:
            return self.get_last_match()

    def wait_gone(self, timeout=None) -> bool:
        """
        Args:
            timeout (float): seconds

        Returns:
            True if gone else False
        """
        deadline = time.time() + (timeout or self._global_timeout)
        while time.time() < deadline:
            if not self.exists:
                return True
            time.sleep(0.2)
        return False

    def click_nowait(self):
        x, y = self.all()[0].center()
        logger.info("click %d, %d", x, y)
        self._parent.send_click(x, y)

    def click(self, timeout=None):
        """find element and perform click"""
        try:
            el = self.get(timeout=timeout)
            el.click()
        except XPathElementNotFoundError:
            if not self._fallback:
                raise
            logger.info("element not found, run fallback")
            return inject_call(self._fallback, d=self._d)

    def click_exists(self, timeout=None) -> bool:
        """return if clicked"""
        try:
            el = self.get(timeout=timeout)
            el.click()
            return True
        except XPathElementNotFoundError:
            return False

    def long_click(self):
        """find element and perform long click"""
        self.get().long_click()

    def screenshot(self) -> Image.Image:
        """take element screenshot"""
        el = self.get()
        return el.screenshot()

    def __getattr__(self, key: str):
        """
        In IPython console, attr:_ipython_canary_method_should_not_exist_ will be called
        So here ignore all attr startswith _
        """
        if key.startswith("_"):
            raise AttributeError("Invalid attr", key)
        el = self.get()
        return getattr(el, key)


class XMLElement(object):
    def __init__(self, elem, parent: XPath):
        """
        Args:
            elem: lxml node
            d: uiautomator2 instance
        """
        self.elem = elem
        self._parent = parent
        self._d = parent._d

    def __hash__(self):
        compared_attrs = ("text", "resource-id", "package", "content-desc")
        values = [self.attrib.get(name) for name in compared_attrs]
        root = self.elem.getroottree()
        fullpath = root.getpath(self.elem)
        fullpath = re.sub(r"\[\d+\]", "", fullpath)  # remove indexes
        values.append(fullpath)
        return hash(tuple(values))

    def __eq__(self, value):
        return self.__hash__() == hash(value)

    def __repr__(self):
        x, y = self.center()
        return "<xpath.XMLElement [{tag!r} center:({x}, {y})]>".format(
            tag=self.elem.tag, x=x, y=y
        )

    def get_xpath(self, strip_index: bool = False):
        """get element full xpath"""
        root = self.elem.getroottree()
        path = root.getpath(self.elem)
        if strip_index:
            path = re.sub(r"\[\d+\]", "", path)  # remove indexes
        return path

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
        click element, 100ms between down and up
        """
        x, y = self.center()
        self._parent.send_click(x, y)

    def long_click(self):
        """
        Sometime long click is needed, 400ms between down and up
        """
        x, y = self.center()
        self._parent.send_longclick(x, y)

    def screenshot(self):
        """
        Take screenshot of element
        """
        im = self._parent.take_screenshot()
        return im.crop(self.bounds)

    def swipe(self, direction: Union[Direction, str], scale: float = 0.6):
        """
        Args:
            direction: one of ["left", "right", "up", "down"]
            scale: percent of swipe, range (0, 1.0)

        Raises:
            AssertionError, ValueError
        """
        return swipe_in_bounds(self._parent._d, self.bounds, direction, scale)

    def scroll(self, direction: Union[Direction, str] = Direction.FORWARD) -> bool:
        """
        Args:
            direction: Direction eg: Direction.FORWARD

        Returns:
            bool: if can be scroll again
        """
        if direction == "forward":
            direction = Direction.FORWARD
        elif direction == "backward":
            direction = Direction.BACKWARD

        els = set(self._parent("//*").all())
        self.swipe(direction, scale=0.6)

        # check if there is more element
        new_elements = set(self._parent("//*").all()) - els
        ppath = self.get_xpath() + "/"  # limit to child nodes
        els = [el for el in new_elements if el.get_xpath().startswith(ppath)]
        return len(els) > 0

    def scroll_to(
        self, xpath: str, direction: Direction = Direction.FORWARD, max_swipes: int = 10
    ) -> Union["XMLElement", None]:
        assert max_swipes > 0
        target = self._parent(xpath)
        for i in range(max_swipes):
            if target.exists:
                return target.get_last_match()
            if not self.scroll(direction):
                break
        return None

    def parent(self, xpath: Optional[str] = None) -> Union["XMLElement", None]:
        """
        Returns parent element
        """
        if xpath is None:
            return XMLElement(self.elem.getparent(), self._parent)

        root = self.elem.getroottree()
        e = self.elem
        els = []
        while e is not None and e != root:
            els.append(e)
            e = e.getparent()

        xpath = strict_xpath(xpath)
        matches = root.xpath(
            xpath, namespaces={"re": "http://exslt.org/regular-expressions"}
        )
        all_paths = [root.getpath(m) for m in matches]
        for e in reversed(els):
            if root.getpath(e) in all_paths:
                return XMLElement(e, self._parent)
            # if e in matches:
            #     return XMLElement(e, self._parent)

    def percent_size(self):
        """Returns:
        (float, float): eg, (0.5, 0.5) means 50%, 50%
        """
        ww, wh = self._d.window_size()
        _, _, w, h = self.rect
        return (w / ww, h / wh)

    @property
    def bounds(self):
        """
        Returns:
            tuple of (left, top, right, bottom)
        """
        bounds = self.elem.attrib.get("bounds")
        lx, ly, rx, ry = map(int, re.findall(r"\d+", bounds))
        return (lx, ly, rx, ry)

    def percent_bounds(self, wsize: Optional[tuple] = None):
        """
        Args:
            wsize (tuple(int, int)): window size

        Returns:
            list of 4 float, eg: 0.1, 0.2, 0.5, 0.8
        """
        lx, ly, rx, ry = self.bounds
        ww, wh = wsize or self._d.window_size()
        return (lx / ww, ly / wh, rx / ww, ry / wh)

    @property
    def rect(self):
        """
        Returns:
            (left_top_x, left_top_y, width, height)
        """
        lx, ly, rx, ry = self.bounds
        return lx, ly, rx - lx, ry - ly

    @property
    def text(self):
        return self.elem.attrib.get("text")

    @property
    def attrib(self):
        return self.elem.attrib

    @property
    def info(self) -> Dict[str, Any]:
        ret = {}
        for key in (
            "text",
            "focusable",
            "enabled",
            "focused",
            "scrollable",
            "selected",
            "clickable",
        ):
            ret[key] = self.attrib.get(key)
        ret["className"] = self.elem.tag
        lx, ly, rx, ry = self.bounds
        ret["bounds"] = {"left": lx, "top": ly, "right": rx, "bottom": ry}
        ret["contentDescription"] = self.attrib.get("content-desc")
        ret["longClickable"] = self.attrib.get("long-clickable")
        ret["packageName"] = self.attrib.get("package")
        ret["resourceName"] = self.attrib.get("resource-id")
        ret["resourceId"] = self.attrib.get(
            "resource-id"
        )  # this is better than resourceName
        ret["childCount"] = len(self.elem.getchildren())
        return ret