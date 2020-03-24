# coding: utf-8
#

import threading

import imageio
from websocket import create_connection

import uiautomator2 as u2


def iter_image_from_minicap(uri):
    ws = create_connection(uri)
    try:
        while True:
            msg = ws.recv()
            if isinstance(msg, str):
                print("<-", msg)
            else:
                yield msg
    finally:
        ws.close()


class Screenrecord:
    def __init__(self, d: u2.Device):
        self._d = d
        self._writer = None

    def __call__(self, filename: str):
        print(filename)
        self._writer = imageio.get_writer(filename, fps=20)
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._start()
        return self

    def _iter_minicap(self):
        ws = create_connection(self._d.path2url("/minicap", scheme="ws"))
        try:
            while not self._stop_event.is_set():
                msg = ws.recv()
                if isinstance(msg, str):
                    # print("<-", msg)
                    pass
                else:
                    yield msg
        finally:
            yield None
            ws.close()

    def _run(self):
        wr = self._writer
        for ws_message in self._iter_minicap():
            if ws_message is None:
                break
            im = imageio.imread(ws_message)
            wr.append_data(im)
        wr.close()
        self._done_event.set()

    def _start(self):
        th = threading.Thread(name="image2video", target=self._run)
        th.daemon = True
        th.start()

    def stop(self):
        """
        Returns:
            bool: whether video is recorded.
        """
        self._stop_event.set()
        ret = self._done_event.wait(10.0)

        # reset
        self._stop_event.clear()
        self._done_event.clear()
        return ret
