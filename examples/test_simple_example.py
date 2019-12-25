# coding: utf-8
#

import uiautomator2 as u2


def test_simple():
    d = u2.connect()
    print(d.info)


if __name__ == "__main__":
    test_simple()
