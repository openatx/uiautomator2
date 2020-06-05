# coding: utf-8
#

import re
import time
import threading

import cv2
import imageio
import numpy as np
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
        self._running = False
        self._stop_event = threading.Event()
        self._done_event = threading.Event()
        self._filename = None
        self._fps = 20  # initial value

    def __call__(self, *args, **kwargs):
        self._start(*args, **kwargs)
        return self

    def _iter_minicap(self):
        http_url = self._d.path2url("/minicap")
        ws_url = re.sub("^http", "ws", http_url)
        ws = create_connection(ws_url)
        try:
            while not self._stop_event.is_set():
                msg = ws.recv()
                if isinstance(msg, str):
                    # print("<-", msg)
                    pass
                else:
                    yield msg
        finally:
            ws.close()

    def _resize_to(self, im, framesize):
        """
        framesize: tuple of (height, width)
        """
        vh, vw = framesize
        h, w = im.shape[:2]
        frame = np.zeros((vh, vw, 3),
                         dtype=np.uint8)  # create black background canvas
        sh = vh / h
        sw = vw / w
        if sh < sw:
            h, w = vh, int(sh * w)
        else:
            h, w = int(sw * h), vw
        left, top = (vw - w) // 2, (vh - h) // 2
        frame[top:top + h, left:left + w, :] = cv2.resize(im, dsize=(w, h))
        return frame

    def _pipe_resize(self, image_iter):
        """ image to same size """
        firstim = next(image_iter)
        yield firstim
        vh, vw = firstim.shape[:2]
        for im in image_iter:
            if im.shape != firstim.shape:
                im = self._resize_to(im, (vh, vw))
            yield im

    def _pipe_convert(self, raw_iter):
        # raw data -> imageio
        for raw in raw_iter:
            yield imageio.imread(raw)

    def _pipe_limit(self, raw_iter):
        findex = 0
        fstart = time.time()
        for raw in raw_iter:
            elapsed = time.time() - fstart
            fcount = int(elapsed * self._fps)
            for _ in range(fcount - findex):
                yield raw
            findex = fcount

    def _run(self):
        pipelines = [self._pipe_limit, self._pipe_convert, self._pipe_resize]
        _iter = self._iter_minicap()
        for p in pipelines:
            _iter = p(_iter)

        with imageio.get_writer(self._filename, fps=self._fps) as wr:
            for im in _iter:
                wr.append_data(im)
        self._done_event.set()

    def _start(self, filename: str, fps: int = 20):
        if self._running:
            raise RuntimeError("screenrecord is already started")

        assert isinstance(fps, int)
        self._filename = filename
        self._fps = fps

        self._running = True
        th = threading.Thread(name="image2video", target=self._run)
        th.daemon = True
        th.start()

    def stop(self):
        """
        stop record and finish write video
        Returns:
            bool: whether video is recorded.
        """
        if not self._running:
            raise RuntimeError("screenrecord is not started")
        self._stop_event.set()
        ret = self._done_event.wait(10.0)

        # reset
        self._stop_event.clear()
        self._done_event.clear()
        self._running = False
        return ret
