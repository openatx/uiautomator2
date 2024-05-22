# coding: utf-8
#

import inspect
import logging
import threading
import time
import typing
from collections import OrderedDict
from typing import List, Optional

import uiautomator2
from uiautomator2.xpath import PageSource, XPathEntry, XPathSelector
from uiautomator2.utils import inject_call

logger = logging.getLogger(__name__)


def _callback_click(el):
    el.click()


class WatchContext:
    def __init__(self, d: "uiautomator2.Device", builtin: bool = False):
        self._d = d
        self._callbacks = OrderedDict()
        self.__xpath_list = []
        self.__lock = threading.Lock()
        self.__trigger_time = time.time()

        # 这里竟然要3个变量记录状态
        self.__stop = threading.Event()
        self.__stopped = threading.Event()  # 结束时设置
        self.__started = False

        if builtin:
            self.when("继续使用").click()
            self.when("移入管控").when("取消").click()
            self.when("^立即(下载|更新)").when("取消").click()
            self.when("同意").click()
            self.when("^(好的|确定)").click()
            self.when("继续安装").click()
            self.when("安装").click()
            self.when("Agree").click()
            self.when("ALLOW").click()

    def wait_stable(self, seconds: float = 5.0, timeout: float = 60.0):
        """ wait until watches not triggered
        Args:
            seconds: stable seconds
            timeout: raise error when wait stable timeout

        Raises:
            TimeoutError
        """
        if not self.__started:
            self.start()

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.__lock:
                if time.time() - self.__trigger_time > seconds:
                    return True
            time.sleep(.2)
        raise TimeoutError("Unstable")

    def when(self, xpath: str):
        """ 当条件满足时,支持 .when(..).when(..) 的级联模式"""
        self.__xpath_list.append(xpath)
        return self

    def call(self, fn: typing.Callable):
        """
        Args:
            fn: support args (d: Device, el: Element)
                see _run_callback function for more details
        """
        xpath_list = tuple(self.__xpath_list)
        self.__xpath_list = []
        assert xpath_list, "when should be called before"

        self._callbacks[xpath_list] = fn

    def click(self):
        self.call(_callback_click)

    def _run(self) -> bool:
        logger.debug("watch check")
        source = self._d.dump_hierarchy()
        for xpaths, func in self._callbacks.items():
            ok = True
            last_match = None
            for xpath in xpaths:
                sel: XPathSelector = self._d.xpath(xpath, source=source)
                if not sel.exists:
                    ok = False
                    break
                last_match = sel.get_last_match()
                logger.debug("match: %s", xpath)
            if ok:
                # 全部匹配
                logger.debug("watchContext xpath matched: %s", xpaths)
                self._run_callback(func, last_match)
                return True
        return False

    def _run_callback(self, func, element):
        inject_call(func, d=self._d, el=element)
        self.__trigger_time = time.time()

    def _run_forever(self, interval: float):
        try:
            while not self.__stop.is_set():
                with self.__lock:
                    self._run()
                time.sleep(interval)
        finally:
            self.__stopped.set()

    def start(self):
        if self.__started:
            return
        self.__started = True
        self.__stop.clear()
        self.__stopped.clear()
        interval = 2.0  # 检查周期
        threading.Thread(target=self._run_forever,
                         daemon=True,
                         args=(interval, )).start()

    def stop(self):
        self.__stop.set()
        self.__stopped.wait(timeout=10)
        self.__started = False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        logger.info("context closed")
        self.stop()


class Watcher():
    def __init__(self, d: "uiautomator2.Device"):
        self._d = d
        self._watchers = []

        self._watch_stop_event = threading.Event()
        self._watch_stopped = threading.Event()
        self._watching = False  # func start is calling
        self._triggering = False

    @property
    def _xpath(self) -> XPathEntry:
        return self._d.xpath

    def _dump_hierarchy(self):
        return self._d.dump_hierarchy()

    def when(self, xpath=None):
        return XPathWatcher(self, xpath)

    def start(self, interval: float = 2.0):
        """ stop watcher """
        if self._watching:
            logger.warning("already started")
            return
        self._watching = True
        th = threading.Thread(name="watcher",
                              target=self._watch_forever,
                              args=(interval, ))
        th.daemon = True
        th.start()
        return th

    def stop(self):
        """ stop watcher """
        if not self._watching:
            logger.warning("watch already stopped")
            return

        if self._watch_stopped.is_set():
            return

        self._watch_stopped.set()
        self._watch_stop_event.wait(timeout=10)

        # reset all status
        self._watching = False
        self._watch_stopped.clear()
        self._watch_stop_event.clear()

    def reset(self):
        """ stop watching and remove all watchers """
        if self._watching:
            self.stop()
        self.remove()

    def running(self) -> bool:
        return self._watching

    @property
    def triggering(self) -> bool:
        return self._triggering

    def _watch_forever(self, interval: float):
        try:
            wait_timeout = interval
            while not self._watch_stopped.wait(timeout=wait_timeout):
                triggered = self.run()
                wait_timeout = min(0.5, interval) if triggered else interval
        finally:
            self._watch_stop_event.set()

    def run(self, source: Optional[PageSource] = None):
        """ run watchers
        Args:
            source: hierarchy content
        """
        if self.triggering:  # avoid to run watcher when run watcher
            return False
        try:
            return self._run_watchers(source=source)
        except Exception as e:
            logger.warning("_run_watchers exception: %s", e)
            return False

    def _run_watchers(self, source=None) -> bool:
        """
        Returns:
            bool (watched or not)
        """
        source = source or self._xpath.get_page_source()

        for h in self._watchers:
            last_selector = None
            for xpath in h['xpaths']:
                last_selector = self._xpath(xpath, source)
                if not last_selector.exists:
                    last_selector = None
                    break

            if last_selector:
                logger.info("XPath(hook:%s): %s", h['name'], h['xpaths'])
                self._triggering = True
                cb = h['callback']
                defaults = {
                    "selector": last_selector,
                    "d": self._d,
                    "source": source,
                }
                st = inspect.signature(cb)
                kwargs = {
                    key: defaults[key]
                    for key in st.parameters.keys() if key in defaults
                }
                ba = st.bind(**kwargs)
                ba.apply_defaults()
                try:
                    cb(*ba.args, **ba.kwargs)
                except Exception as e:
                    logger.warning("watchers exception: %s", e)
                finally:
                    self._triggering = False
                return True
        return False

    def __call__(self, name: str) -> "XPathWatcher":
        return XPathWatcher(self, None, name)

    def remove(self, name=None):
        """ remove watcher """
        if name is None:
            self._watchers = []
            return
        for w in self._watchers[:]:
            if w['name'] == name:
                logger.debug("remove(%s) %s", name, w['xpaths'])
                self._watchers.remove(w)


class XPathWatcher():
    def __init__(self, parent: Watcher, xpath: str, name: str = ''):
        self._name = name
        self._parent = parent
        self._xpath_list: List[str] = [xpath] if xpath else []

    def when(self, xpath: str = None):
        self._xpath_list.append(xpath)
        return self

    def call(self, func: callable):
        """
        func accept argument, key(d, el)
        d=self._d, el=element
        """
        self._parent._watchers.append({
            "name": self._name,
            "xpaths": self._xpath_list,
            "callback": func,
        })

    def click(self):
        def _inner_click(selector: XPathSelector):
            selector.get_last_match().click()

        self.call(_inner_click)

    def press(self, key):
        """
        key (str): on of
            ("home", "back", "left", "right", "up", "down", "center",
            "search", "enter", "delete", "del", "recent", "volume_up",
            "menu", "volume_down", "volume_mute", "camera", "power")
        """
        def _inner_press(d: "uiautomator2.Device"):
            d.press(key)

        self.call(_inner_press)
