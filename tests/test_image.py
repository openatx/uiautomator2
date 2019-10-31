# coding: utf-8
#

import os
import uiautomator2.image as u2image


def test_imread():
    im = u2image.imread("https://www.baidu.com/img/bd_logo1.png")
    assert im.shape == (258, 540, 3)

    __dir__ = os.path.dirname(os.path.abspath(__file__))

    filepath = os.path.join(__dir__, "./testdata/AE86.jpg")
    im = u2image.imread(filepath)
    assert im.shape == (193, 321, 3)

    pim = u2image.cv2pil(im)
    assert pim.size == (321, 193)


