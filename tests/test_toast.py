# coding: utf-8
#
# Test apk Download from
# https://github.com/appium/java-client/raw/master/src/test/java/io/appium/java_client/ApiDemos-debug.apk

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

    def test_scroll(self):
        d = self.sess
        d(text="App").click()
        d(scrollable=True).scroll.to(text="Voice Recognition")

    def test_watchers(self):
        """
        App -> Notification -> Status Bar
        """
        d = self.sess
        d.watchers.remove()
        d.watchers.watched = False

        d.watcher("N").when(text='Notification').click(text='Notification')
        d(text="App").click()
        d.watchers.run()
        self.assertTrue(d(text="Status Bar").wait(timeout=3))
        d.press("back")
        d.press("back")
        # Should auto click Notification when show up
        self.assertFalse(d.watchers.watched)
        d.watchers.watched = True
        self.assertTrue(d.watchers.watched)
        d(text="App").click()
        self.assertTrue(d(text="Status Bar").exists(timeout=3))
        d.watchers.watched = False


if __name__ == '__main__':
    unittest.main()
