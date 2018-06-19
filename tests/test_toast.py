# coding: utf-8
#

import uiautomator2 as u2
import unittest
import time


class ToastTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = u2.connect_usb()

    def setUp(self):
        self.sess = self.d.session("io.appium.android.apis")

    def test_toast_get_message(self):
        d = self.sess
        d.toast.reset()
        assert d.toast.get_message(0) is None
        assert d.toast.get_message(0, default="d") == "d"
        d(text="App").click()
        d(text="Notification").click()
        d(text="NotifyWithText").click()
        d(text="Show Short Notification").click()
        self.assertEqual(d.toast.get_message(2, 5, ""), "Short notification")
        time.sleep(.5)
        self.assertIsNone(d.toast.get_message(0, 0.4))
        # d.toast.reset()
        # d.toast.show("Hello world")
        # self.assertEqual(d.toast.get_message(5, 5), "Hello world")


if __name__ == '__main__':
    unittest.main()
