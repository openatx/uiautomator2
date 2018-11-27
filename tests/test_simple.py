# coding: utf-8
#
# Test apk Download from
# https://github.com/appium/java-client/raw/master/src/test/java/io/appium/java_client/ApiDemos-debug.apk

import uiautomator2 as u2
import unittest
import time


class SimpleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = u2.connect()
        cls.d.set_orientation('natural')
        cls.d.implicitly_wait(10)

    def setUp(self):
        self.sess = self.d.session("io.appium.android.apis")
        self.sess.watchers.remove()

    def tearDown(self):
        self.sess.watchers.remove()

    def test_toast_get_message(self):
        d = self.sess
        d.toast.reset()
        assert d.toast.get_message(0) is None
        assert d.toast.get_message(0, default="d") == "d"
        d(text="App").click()
        d(text="Notification").click()
        d(text="NotifyWithText").click()
        try:
            d(text="Show Short Notification").click()
        except u2.UiObjectNotFoundError:
            d(text="SHOW SHORT NOTIFICATION").click()
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

    def test_count(self):
        d = self.sess
        count = d(resourceId="android:id/list").child(
            className="android.widget.TextView").count
        self.assertEqual(count, 11)
        self.assertEqual(
            d(resourceId="android:id/list").info['childCount'], 11)
        count = d(resourceId="android:id/list").child(
            className="android.widget.TextView", instance=0).count
        self.assertEqual(count, 1)

    def test_get_text(self):
        d = self.sess
        text = d(resourceId="android:id/list").child(
            className="android.widget.TextView", instance=2).get_text()
        self.assertEqual(text, "App")

    def test_xpath(self):
        d = self.sess
        self.assertEqual(len(d.xpath("//*[@text='Media']").all()), 1)
        self.assertEqual(len(d.xpath("//*[@text='MediaNotExists']").all()), 0)
        d.xpath("//*[@text='Media']").click()
        self.assertTrue(d.xpath('//*[contains(@text, "Audio")]').wait(5))

    def test_implicitly_wait(self):
        d = self.sess
        d.implicitly_wait(2)
        self.assertEqual(d.implicitly_wait(), 2)
        start = time.time()
        with self.assertRaises(u2.UiObjectNotFoundError):
            d(text="Sensors").get_text()
        time_used = time.time() - start
        self.assertGreaterEqual(time_used, 2)
        # maybe longer then 2, waitForExists -> getText
        # getText may take 1~2s
        self.assertLess(time_used, 2 + 3)

    def test_select_iter(self):
        d = self.sess
        d(text='OS').click()
        texts = d(resourceId='android:id/list').child(
            className='android.widget.TextView')
        self.assertEqual(texts.count, 4)
        words = []
        for item in texts:
            words.append(item.get_text())
        self.assertEqual(
            words,
            ['Morse Code', 'Rotation Vector', 'Sensors', 'SMS Messaging'])

    def test_plugin(self):
        def _my_plugin(d, k):
            def _inner():
                return k

            return _inner

        u2.plugin_clear()
        u2.plugin_register('my', _my_plugin, 'pp')
        self.assertEqual(self.d.ext_my(), 'pp')


if __name__ == '__main__':
    unittest.main()
