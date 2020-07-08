# coding: utf-8
#

import inspect
import logging
import threading
from typing import Optional

from logzero import setup_logger

import uiautomator2
from uiautomator2.xpath import XPath


class Watcher():
    def __init__(self, d: "uiautomator2.Device"):
        self._d = d
        self._watchers = []

        self._watch_stop_event = threading.Event()
        self._watch_stopped = threading.Event()
        self._watching = False  # func start is calling
        self._triggering = False

        self.logger = setup_logger()
        self.logger.setLevel(logging.INFO)

    @property
    def debug(self):
        return self.logger.level == logging.DEBUG

    @debug.setter
    def debug(self, v: bool):
        assert isinstance(v, bool)
        self.logger.setLevel(logging.DEBUG if v else logging.INFO)

    @property
    def _xpath(self) -> XPath:
        return self._d.xpath

    def _dump_hierarchy(self):
        return self._d.dump_hierarchy()

    def when(self, xpath=None):
        return XPathWatcher(self, xpath)

    def start(self, interval: float = 2.0):
        """ stop watcher """
        if self._watching:
            self.logger.warning("already started")
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
            self.logger.warning("watch already stopped")
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

    def run(self, source: Optional[str] = None):
        """ run watchers
        Args:
            source: hierarchy content
        """
        if self.triggering:  # avoid to run watcher when run watcher
            return False
        return self._run_watchers(source=source)

    def _run_watchers(self, source=None) -> bool:
        """
        Returns:
            bool (watched or not)
        """
        source = source or self._dump_hierarchy()

        for h in self._watchers:
            last_selector = None
            for xpath in h['xpaths']:
                last_selector = self._xpath(xpath, source)
                if not last_selector.exists:
                    last_selector = None
                    break

            if last_selector:
                self.logger.info("XPath(hook:%s): %s", h['name'], h['xpaths'])
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
                    self.logger.warning("watchers exception: %s", e)
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
                self.logger.debug("remove(%s) %s", name, w['xpaths'])
                self._watchers.remove(w)


class XPathWatcher():
    def __init__(self, parent: Watcher, xpath: str, name: str = ''):
        self._name = name
        self._parent = parent
        self._xpath_list = [xpath] if xpath else []

    def when(self, xpath=None):
        self._xpath_list.append(xpath)
        return self

    def call(self, func):
        self._parent._watchers.append({
            "name": self._name,
            "xpaths": self._xpath_list,
            "callback": func,
        })

    def click(self):
        def _inner_click(selector):
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
