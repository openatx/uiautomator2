# coding: utf-8
#
# Test apk Download from
# https://github.com/appium/java-client/raw/master/src/test/java/io/appium/java_client/ApiDemos-debug.apk

import time
import unittest

import pytest

import uiautomator2 as u2


@pytest.mark.skip("not working")
def test_toast_get_message(sess: u2.Device):
    d = sess
    assert d.toast.get_message(0) is None
    assert d.toast.get_message(0, default="d") == "d"
    d(text="App").click()
    d(text="Notification").click()
    d(text="NotifyWithText").click()
    try:
        d(text="Show Short Notification").click()
    except u2.UiObjectNotFoundError:
        d(text="SHOW SHORT NOTIFICATION").click()
    #self.assertEqual(d.toast.get_message(2, 5, ""), "Short notification")
    assert "Short notification" in d.toast.get_message(2, 5, "")
    time.sleep(.5)
    assert d.toast.get_message(0, 0.4)


def test_scroll(sess: u2.Device):
    d = sess
    d(text="App").click()
    if not d(scrollable=True).exists:
        pytest.skip("screen to large, no need to scroll")
    d(scrollable=True).scroll.to(text="Voice Recognition")


@pytest.mark.skip("Need upgrade")
def test_watchers(self):
    """
    App -> Notification -> Status Bar
    """
    d = self.sess
    d.watcher.remove()
    d.watcher.stop()

    d(text="App").click()
    d.xpath("Notification").wait()
    
    d.watcher("N").when('Notification').click()
    d.watcher.run()

    self.assertTrue(d(text="Status Bar").wait(timeout=3))
    d.press("back")
    d.press("back")
    # Should auto click Notification when show up
    self.assertFalse(d.watcher.running())
    d.watcher.start()

    self.assertTrue(d.watcher.running())
    d(text="App").click()
    self.assertTrue(d(text="Status Bar").exists(timeout=5))

    d.watcher.remove("N")
    d.press("back")
    d.press("back")

    d(text="App").click()
    self.assertFalse(d(text="Status Bar").wait(timeout=5))


@pytest.mark.skip("TODO:: not fixed")
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

def test_get_text(sess):
    d = sess
    text = d(resourceId="android:id/list").child(
        className="android.widget.TextView", instance=2).get_text()
    assert text == "App"


def test_xpath(sess):
    d = sess
    d.xpath("//*[@text='Media']").wait()
    assert len(d.xpath("//*[@text='Media']").all()) == 1
    assert len(d.xpath("//*[@text='MediaNotExists']").all()) == 0
    d.xpath("//*[@text='Media']").click()
    assert d.xpath('//*[contains(@text, "Audio")]').wait(5)


@pytest.mark.skip("Need fix")
def test_implicitly_wait(d):
    d.implicitly_wait(2)
    assert d.implicitly_wait() == 2
    start = time.time()
    with self.assertRaises(u2.UiObjectNotFoundError):
        d(text="Sensors").get_text()
    time_used = time.time() - start
    assert time_used >= 2
    # maybe longer then 2, waitForExists -> getText
    # getText may take 1~2s
    assert time_used < 2 + 3

@pytest.mark.skip("TODO:: not fixed")
def test_select_iter(d):
    d(text='OS').click()
    texts = d(resourceId='android:id/list').child(
        className='android.widget.TextView')
    assert texts.count == 4
    words = []
    for item in texts:
        words.append(item.get_text())
    assert words == ['Morse Code', 'Rotation Vector', 'Sensors', 'SMS Messaging']


@pytest.mark.skip("Deprecated")
def test_plugin(self):
    def _my_plugin(d, k):
        def _inner():
            return k

        return _inner

    u2.plugin_clear()
    u2.plugin_register('my', _my_plugin, 'pp')
    self.assertEqual(self.d.ext_my(), 'pp')

def test_send_keys(sess):
    d = sess
    d.xpath("App").click()
    d.xpath("Search").click()
    d.xpath('//*[@text="Invoke Search"]').click()
    d.send_keys("hello", clear=True)
    assert d.xpath('io.appium.android.apis:id/txt_query_prefill').info['text'] == 'hello'


if __name__ == '__main__':
    unittest.main()
