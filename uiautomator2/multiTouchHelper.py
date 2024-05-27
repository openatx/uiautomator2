from math import cos, sin, pi
from uiautomator2 import Device
from uiautomator2 import PointerInput, Sequence, Pause
from typing import List

class multiTouchHelper:
    def __init__(self, device: Device):
        self.device = device

    def zoom_singlefinger(self, finger_name: str, locus: tuple, start_radius: int, end_radius: int, angle: float, duration: int) -> Sequence:
        finger = PointerInput(PointerInput.Kind.TOUCH, finger_name)
        finger_path = Sequence(finger, 0)

        midpoint_radius = start_radius + (end_radius > start_radius) * 20

        finger_startx = int(locus[0] + start_radius * cos(angle))
        finger_starty = int(locus[1] - start_radius * sin(angle))

        finger_midx = int(locus[0] + midpoint_radius * cos(angle))
        finger_midy = int(locus[1] - midpoint_radius * sin(angle))

        finger_endx = int(locus[0] + end_radius * cos(angle))
        finger_endy = int(locus[1] - end_radius * sin(angle))

        finger_path.addAction(finger.createPointerMove(0, PointerInput.Origin.viewport(), finger_startx, finger_starty))
        finger_path.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()))
        finger_path.addAction(finger.createPointerMove(1, PointerInput.Origin.viewport(), finger_midx, finger_midy))
        finger_path.addAction(Pause(finger, 100))
        finger_path.addAction(finger.createPointerMove(duration, PointerInput.Origin.viewport(), finger_endx, finger_endy))
        finger_path.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()))

        return finger_path

    def zoom(self, locus: tuple, start_radius: int, end_radius: int, pinch_angle: int, duration: int) -> List[Sequence]:
        angle = pi / 2 - (2 * pi / 360 * pinch_angle)

        finger_a_path = self.zoom_singlefinger("fingerA", locus, start_radius, end_radius, angle, duration)

        angle += pi
        finger_b_path = self.zoom_singlefinger("fingerB", locus, start_radius, end_radius, angle, duration)

        return [finger_a_path, finger_b_path]

    def rotate_singlefinger(self, finger_name: str, locus: tuple, start_angle: float, end_angle: float, radius: int, duration: int) -> Sequence:
        finger = PointerInput(PointerInput.Kind.TOUCH, finger_name)
        finger_path = Sequence(finger, 0)

        finger_startx = int(locus[0] + radius * cos(start_angle))
        finger_starty = int(locus[1] - radius * sin(start_angle))

        finger_endx = int(locus[0] + radius * cos(end_angle))
        finger_endy = int(locus[1] - radius * sin(end_angle))

        finger_path.addAction(finger.createPointerMove(0, PointerInput.Origin.viewport(), finger_startx, finger_starty))
        finger_path.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()))
        finger_path.addAction(finger.createPointerMove(duration, PointerInput.Origin.viewport(), finger_endx, finger_endy))
        finger_path.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()))

        return finger_path

    def rotate(self, locus: tuple, start_angle: float, end_angle: float, radius: int, duration: int) -> List[Sequence]:
        finger_a_path = self.rotate_singlefinger("fingerA", locus, start_angle, end_angle, radius, duration)

        finger_b_start_angle = start_angle + pi / 2
        finger_b_end_angle = end_angle + pi / 2
        finger_b_path = self.rotate_singlefinger("fingerB", locus, finger_b_start_angle, finger_b_end_angle, radius, duration)

        return [finger_a_path, finger_b_path]

    def rotate_clockwise(self, locus: tuple, angle: float):
        self.device.perform(self.rotate(locus, 0, angle, 15, 25))

    def rotate_counter_clockwise(self, locus: tuple, angle: float):
        self.device.perform(self.rotate(locus, 0, -angle, 15, 25))
