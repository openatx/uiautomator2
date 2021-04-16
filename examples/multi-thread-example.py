# coding: utf-8
#
# GIL limit python multi-thread effectiveness.
# But is seems fine, because these operation have so many socket IO
# So  it seems no need to use multiprocess
#
import uiautomator2 as u2
import adbutils
import threading
from logzero import logger


def worker(d: u2.Device):
    d.app_start("io.appium.android.apis", stop=True)
    d(text="App").wait()
    for el in d.xpath("@android:id/list").child("/android.widget.TextView").all():
        logger.info("%s click %s", d.serial, el.text)
        el.click()
        d.press("back")
    logger.info("%s DONE", d.serial)


for dev in adbutils.adb.device_list():
    print("Dev:", dev)
    d = u2.connect(dev.serial)
    t = threading.Thread(target=worker, args=(d,))
    t.start()
