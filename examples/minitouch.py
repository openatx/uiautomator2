# coding: utf-8
#
# 半成品
import json

from websocket import create_connection

from . import Device


class Minitouch:
    # TODO: need test
    def __init__(self, d: Device):
        self._d = d
        self._prepare()

    def _prepare(self):
        self._w, self._h = self._d.window_size()
        uri = self._d.path2url("/minitouch").replace("http:", "ws:")
        self._ws = create_connection(uri)
        # self._reset()

    def down(self, x, y, index: int = 0):
        px = x / self._w
        py = y / self._h
        self._ws_send({"operation": "d", "index": index, "xP": px, "yP": py, "pressure": 0.5})
        self._commit()

    def move(self, x, y, index: int = 0):
        px = x / self._w
        py = y / self._h
        self._ws_send({"operation": "m", "index": index, "xP": px, "yP": py, "pressure": 0.5})

    def up(self, x, y, index: int = 0):
        self._ws_send({"operation": "u", "index": index})
        self._commit()

    def click(self, x, y):
        self.down(x, y)
        self.up(x, y)

    def pinch_in(self, x, y, radius: int, steps: int = 10):
        """
        Args:
            x, y: center point
        """
        pass

    def _reset(self):
        self._ws_send({"operation": "r"}) # reset

    def _commit(self):
        self._ws_send({"operation": "c"})

    def _ws_send(self, payload: dict):
        from pprint import pprint
        pprint(payload)
        self._ws.send(json.dumps(payload), opcode=1)
