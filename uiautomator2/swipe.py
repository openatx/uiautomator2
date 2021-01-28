# coding: utf-8

from typing import Union
from ._proto import Direction


class SwipeExt(object):
    def __init__(self, d):
        """
        Args：
            d (uiautomator2.Device)
        """
        self._d = d

    def __call__(self,
                 direction: Union[Direction, str],
                 scale: float = 0.9,
                 box: Union[None, tuple] = None,
                 **kwargs):
        """
        Args:
            direction (str): one of "left", "right", "up", "bottom" or Direction.LEFT
            scale (float): percent of swipe, range (0, 1.0]
            box (tuple): None or [lx, ly, rx, ry]
            kwargs: used as kwargs in d.swipe

        Raises:
            ValueError
        """
        def _swipe(_from, _to):
            self._d.swipe(_from[0], _from[1], _to[0], _to[1], **kwargs)

        if box:
            lx, ly, rx, ry = box
        else:
            lx, ly = 0, 0
            rx, ry = self._d.window_size()

        width, height = rx - lx, ry - ly

        h_offset = int(width * (1 - scale)) // 2
        v_offset = int(height * (1 - scale)) // 2

        center = lx + width//2, ly + height//2
        left = lx + h_offset, ly + height // 2
        up = lx + width // 2, ly + v_offset
        right = rx - h_offset, ly + height // 2
        bottom = lx + width // 2, ry - v_offset

        if direction == Direction.LEFT:
            _swipe(right, left)
        elif direction == Direction.RIGHT:
            _swipe(left, right)
        elif direction == Direction.UP:
            _swipe(center, up) # from center to top
        elif direction == Direction.DOWN:
            _swipe(center, bottom) # from center to bottom
        else:
            raise ValueError("Unknown direction:", direction)
