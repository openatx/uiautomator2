import enum

SCROLL_STEPS = 55
HTTP_TIMEOUT = 60

class Direction(str, enum.Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"

    # 垂直操作
    FORWARD = "up"
    BACKWARD = "down"

    # 水平操作
    HORIZ_FORWARD = "left"
    HORIZ_BACKWARD = "right"