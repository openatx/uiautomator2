# coding: utf-8
#

from __future__ import absolute_import

import abc
import copy
import enum
import functools
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from PIL import Image
from lxml import etree

from uiautomator2._proto import Direction
from uiautomator2.abstract import AbstractXPathBasedDevice
from uiautomator2.exceptions import XPathElementNotFoundError
from uiautomator2.utils import inject_call, swipe_in_bounds, deprecated


logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    pass


class XPathError(Exception):
    """basic error for xpath plugin"""



def safe_xmlstr(s: str) -> str:
    s = re.sub('[$@#&]', '.', s)
    s = re.sub('\\.+', '.', s)
    s = re.sub('^\\.|\\.$', '', s)
    return s


def string_quote(s: str) -> str:
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


def convert_to_camel_case(s: str) -> str:
    """
    Convert a string from kebab-case to camelCase.

    Example:
        "hello-world" -> "helloWorld"
    """
    parts = s.split('-')
    # Convert the first letter of each part to uppercase, except for the first part
    camel_case_str = parts[0] + ''.join(part.capitalize() for part in parts[1:])
    return camel_case_str


def strict_xpath(xpath: str) -> str:
    """make xpath to be computer recognized xpath"""
    orig_xpath = xpath

    if xpath.lstrip("(").startswith("/"):
        pass
    elif xpath.startswith("@"):
        xpath = "//*[@resource-id={!r}]".format(xpath[1:])
    elif xpath.startswith("^"):
        xpath = "//*[re:match(@text, {0}) or re:match(@content-desc, {0}) or re:match(@resource-id, {0})]".format(
            string_quote(xpath)
        )
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

    xpath = xpath.rstrip("/")
    if not is_xpath_syntax_ok(xpath):
        raise XPathError("Invalid xpath", orig_xpath)
    logger.debug("xpath %s -> %s", orig_xpath, xpath)
    return xpath


class XPath(str):
    def __new__(cls, value, *args):
        if isinstance(value, XPath):
            return value
        xpath = strict_xpath(value)
        if args:
            return functools.reduce(lambda a, b: a.joinpath(b), args, XPath(xpath))
        else:
            return super().__new__(cls, xpath)
    
    def __repr__(self):
        return f'XPath({super().__repr__()})'

    def __and__(self, value: 'XPath') -> 'XPathSelector':
        raise NotImplementedError

    def joinpath(self, subpath: str) -> "XPath":
        if not subpath.startswith('/'):
            subpath = '/' + subpath
        return XPath(self + subpath)
    

class PageSource:
    def __init__(self, xml_content: str):
        self._xml_content = xml_content
    
    @staticmethod
    def parse(data: Optional[Union[str, "PageSource"]]) -> Optional["PageSource"]:
        if not data:
            return None
        if isinstance(data, str):
            return PageSource(data)
        return data
    
    @functools.cached_property
    def root(self) -> etree._Element:
        _root = etree.fromstring(str2bytes(self._xml_content))
        for node in _root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class", "")) or "node"
        return _root

    def find_elements(self, xpath: Union[str, XPath]) -> List["XMLElement"]:
        matches = self.root.xpath(xpath, namespaces={"re": "http://exslt.org/regular-expressions"})
        return [XMLElement(node) for node in matches]


class XPathEntry(object):
    def __init__(self, d: AbstractXPathBasedDevice):
        """
        Args:
            d (uiautomator2 instance)
        """
        self._d = d
        assert hasattr(d, "wait_timeout")
        # TODO: remove wait_timeout

    def global_set(self, key, value):
        valid_keys = {
            "timeout",
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

    def get_page_source(self) -> PageSource:
        return PageSource.parse(self._d.dump_hierarchy())

    def match(self, xpath, source=None):
        return len(self(xpath, source).all()) > 0

    @deprecated(reason="use d.watcher.when(..) instead")
    def when(self, xquery: str):
        return self._watcher.when(xquery)

    @deprecated(reason="use d.watcher.run() instead")
    def run_watchers(self, source=None):
        self._watcher.run()

    @deprecated(reason="use d.watcher.start(..) instead")
    def watch_background(self, interval: float = 4.0):
        return self._watcher.start(interval)

    @deprecated(reason="use d.watcher.stop() instead")
    def watch_stop(self):
        """stop watch background"""
        self._watcher.stop()

    @deprecated(reason="use d.watcher.remove() instead")
    def watch_clear(self):
        self._watcher.stop()

    @deprecated(reason="removed")
    def sleep_watch(self, seconds):
        """run watchers when sleep"""
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.run_watchers()
            left_time = max(0, deadline - time.time())
            time.sleep(min(0.5, left_time))

    def click(self, xpath: Union[str, list], timeout: float=None):
        """
        Find element and perform click

        Args:
            xpath (str): xpath string
            timeout (float): pass
            pre_delay (float): pre delay wait time before click

        Raises:
            TimeoutException
        """
        selector = XPathSelector(xpath, self)
        selector.click(timeout=timeout)

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
        elif direction == Direction.HORIZ_BACKWARD:
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

    def __call__(self, xpath: str, source: Union[str, PageSource] = None) -> "XPathSelector":
        return XPathSelector(xpath, self, PageSource.parse(source))


class Operator(str, enum.Enum):
    AND = 'AND'
    OR = 'OR'


class AbstractSelector(abc.ABC):
    @abc.abstractmethod
    def all(self, source: PageSource) -> List['XMLElement']:
        pass
    

class XPathSelector(AbstractSelector):
    def __init__(self, xpath: Union[str, XPath, AbstractSelector], parent: XPathEntry = None, source: Optional[PageSource] = None):
        self._base_xpath = XPath(xpath) if isinstance(xpath, str) else xpath
        self._operator: Operator = None
        self._next_xpath: AbstractSelector = None

        self._parent = parent
        self._source = source
        self._last_source: Optional[PageSource] = None
        self._fallback: callable = None
    
    def copy(self) -> "XPathSelector":
        """copy self"""
        return copy.copy(self)
    
    @classmethod
    def create(cls, value: Union[str, XPath, 'XPathSelector']) -> 'XPathSelector':
        if isinstance(value, XPathSelector):
            return value.copy()
        elif isinstance(value, (str, XPath)):
            return XPathSelector(XPath(value))
        else:
            raise ValueError('Invalid value', value)

    def __repr__(self):
        if self._operator:
            return f'XPathSelector({repr(self._base_xpath)} {self._operator.value} {repr(self._next_xpath)})'
        else:
            return f'XPathSelector({repr(self._base_xpath)})'
    
    def __and__(self, value) -> 'XPathSelector':
        s = XPathSelector(self)
        s._next_xpath = XPathSelector.create(value)
        s._operator = Operator.AND
        s._parent = self._parent
        return s

    def __or__(self, value) -> 'XPathSelector':
        s = XPathSelector(self)
        s._next_xpath = XPathSelector.create(value)
        s._operator = Operator.OR
        s._parent = self._parent
        return s

    def xpath(self, _xpath: Union[list, tuple, str]) -> 'XPathSelector':
        """
        add xpath to condition list
        the element should match all conditions

        Deprecated, using a & b instead
        """
        if isinstance(_xpath, (list, tuple)):
            return functools.reduce(lambda a, b: a & b, _xpath, self)
        else:
            return self & _xpath

    def child(self, _xpath: str) -> "XPathSelector":
        """
        add child xpath
        """
        if self._operator or not isinstance(self._base_xpath, XPath):
            raise XPathError("can't use child when base is not XPath or operator is set")
        new = self.copy()
        new._base_xpath = self._base_xpath.joinpath(_xpath)
        return new

    def fallback(self, func: Optional[Callable[..., bool]] = None, *args, **kwargs):
        """
        callback on failure
        """
        if not callable(func):
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

    def _get_page_source(self) -> PageSource:
        if self._source:
            return self._source
        if not self._parent:
            raise XPathError("self._parent is not set")
        return self._parent.get_page_source()
    
    def all(self, source: PageSource=None) -> List["XMLElement"]:
        """find all matched elements"""
        if not source:
            source = self._get_page_source()
        self._last_source = source

        elements = []
        if isinstance(self._base_xpath, XPath):
            elements = source.find_elements(self._base_xpath)
        else:
            elements = self._base_xpath.all(source)

        # AND OR
        if self._next_xpath and self._operator:
            next_els = self._next_xpath.all(source)
            if self._operator == Operator.AND:
                elements = list(set(elements) & set(next_els))
            elif self._operator == Operator.OR:
                elements = list(set(elements) | set(next_els))
            else:
                raise ValueError("Invalid operator", self._operator)
        for el in elements:
            el._parent = self._parent
        return elements

    @property
    def exists(self) -> bool:
        return len(self.all()) > 0

    def get(self, timeout=None) -> "XMLElement":
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
            raise XPathElementNotFoundError(self)
        return self.get_last_match()

    def get_last_match(self) -> "XMLElement":
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

    def set_text(self, text: str):
        el = self.get()
        el.click()  # focus input-area
        self._parent._d.send_keys(text)

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
        self._parent._d.click(x, y)

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
        if not hasattr(XMLElement, key):
            raise AttributeError("Invalid attr", key)
        el = self.get()
        return getattr(el, key)


class XMLElement(object):
    def __init__(self, elem: etree._Element, parent: XPathEntry = None):
        """
        Args:
            elem: lxml node
            d: uiautomator2 instance
        """
        self.elem = elem
        self._parent = parent

    def __hash__(self):
        return hash(self.elem)

    def __eq__(self, value):
        return self.__hash__() == hash(value)

    def __repr__(self):
        x, y = self.center()
        return "<XMLElement [{tag!r} center:({x}, {y})]>".format(
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
        self._parent._d.click(x, y)

    def long_click(self):
        """
        Sometime long click is needed, 400ms between down and up
        """
        x, y = self.center()
        self._parent._d.long_click(x, y)

    def screenshot(self):
        """
        Take screenshot of element
        """
        im = self._parent._d.screenshot()
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
        ww, wh = self._parent._d.window_size()
        _, _, w, h = self.rect
        return (w / ww, h / wh)

    @functools.cached_property
    def bounds(self) -> Tuple[int, int, int, int]:
        """
        Returns:
            tuple of (left, top, right, bottom)
        """
        bounds = self.elem.attrib.get("bounds")
        if not bounds:
            return (0, 0, 0, 0)
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
        ww, wh = wsize or self._parent._d.window_size()
        return (lx / ww, ly / wh, rx / ww, ry / wh)

    @property
    def rect(self) -> Tuple[int, int, int, int]:
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
        for k, v in dict(self.attrib).items():
            if k in ("bounds", "class", "package", "content-desc"):
                continue
            if k in ("checkable", "checked", "clickable", "enabled", "focusable", "focused", "scrollable",
                     "long-clickable", "password", "selected", "visible-to-user"):
                ret[convert_to_camel_case(k)] = v == "true"
            elif k == "index":
                ret[k] = int(v)
            else:
                ret[convert_to_camel_case(k)] = v

        ret["childCount"] = len(self.elem.getchildren())
        ret["className"] = self.elem.tag
        lx, ly, rx, ry = self.bounds
        ret["bounds"] = {"left": lx, "top": ly, "right": rx, "bottom": ry}

        # 名字命名的有点奇怪，为了兼容性暂时保留
        ret["packageName"] = self.attrib.get("package")
        ret["contentDescription"] = self.attrib.get("content-desc")
        ret["resourceName"] = self.attrib.get("resource-id")
        return ret
