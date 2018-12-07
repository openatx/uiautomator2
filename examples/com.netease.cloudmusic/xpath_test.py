# coding: utf-8
#

import unittest
from logzero import logger

import uiautomator2 as u2

d = u2.connect_usb("3578298f")

class MusicTestCase(unittest.TestCase):
    def setUp(self):
        logger.info("setUp unlock-screen")
        # unlock screen
        d.shell("input keyevent WAKEUP")
        d.shell("input keyevent HOME")
        # d.screen_on()
        d.swipe(0.1, 0.9, 0.9, 0.1)

    def runTest(self):
        logger.info("runTest")
        d.app_clear("com.netease.cloudmusic")
        s = d.session("com.netease.cloudmusic")
        s.set_fastinput_ime(True)

        xp = d.ext_xpath
        xp._d = s


        # 处理弹窗
        xp.when("跳过").click()
        xp.when("允许").click() # 系统弹窗
        # xp.when("@com.tencent.ibg.joox:id/btn_dismiss").click()

        xp("立即体验").click()
        print("Search")
        xp("搜索").click()
        s.send_keys("周杰伦")
        s.send_action("search")
        # xp("@com.tencent.ibg.joox:id/search_area").click()
        # xp("@com.tencent.ibg.joox:id/searchItem").click()
        # s.send_keys("One Call Away")
        # s.send_action("search")
    
    def tearDown(self):
        d.set_fastinput_ime(False)


if __name__ == "__main__":
    unittest.main()
     