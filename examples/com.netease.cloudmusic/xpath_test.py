# coding: utf-8
#

import unittest
from logzero import logger

import uiautomator2 as u2

# d = u2.connect_usb("3578298f")
d = u2.connect_usb()

class MusicTestCase(unittest.TestCase):
    def setUp(self):
        self.package_name = "com.netease.cloudmusic"
        d.ext_xpath.global_set({"timeout": 10})
        logger.info("setUp unlock-screen")
        # unlock screen
        # d.shell("input keyevent WAKEUP")
        d.screen_on()
        d.shell("input keyevent HOME")
        d.swipe(0.1, 0.9, 0.9, 0.1) # swipe to unlock

    def runTest(self):
        logger.info("runTest")
        d.app_clear(self.package_name)
        s = d.session(self.package_name)
        s.set_fastinput_ime(True)

        xp = d.ext_xpath
        xp._d = s

        # 处理弹窗
        xp.when("跳过").click()
        xp.when("允许").click() # 系统弹窗
        # xp.when("@com.tencent.ibg.joox:id/btn_dismiss").click()

        xp("立即体验").click()
        logger.info("Search")
        xp("搜索").click()
        s.send_keys("周杰伦")
        s.send_action("search")
        self.assertTrue(xp("布拉格广场").wait())
        # xp("@com.tencent.ibg.joox:id/search_area").click()
        # xp("@com.tencent.ibg.joox:id/searchItem").click()
        # s.send_keys("One Call Away")
        # s.send_action("search")
    
    def tearDown(self):
        d.set_fastinput_ime(False)
        d.app_stop(self.package_name)
        d.screen_off()

if __name__ == "__main__":
    unittest.main()
     