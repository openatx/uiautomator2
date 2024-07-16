# coding: utf-8
#
# Not implemented yet.
#
import json
import logging
import string
from pprint import pprint

import adbutils
import pychrome
import requests

logger = logging.getLogger(__name__)

class WebviewDriver():
    def __init__(self, url):
        self._url = url
        self._browser = pychrome.Browser(self._url)

    @property
    def browser(self):
        """ new Browser all the time to clear history data """
        return self._browser

    def get_active_tab_list(self):
        tabs = []
        for tab in self.browser.list_tab():
            logger.debug("tab: %s", tab)
            tab.start()
            t = BrowserTab(tab)
            if t.is_activate():
                tabs.append(t)
            else:
                tab.stop()
        return tabs
    
    def get_activate_tab(self):
        pass


class BrowserTab():
    def __init__(self, tab):
        self._tab = tab
        # I donot know why should call, Runtime.enable() ..., as I know, chromedriver call that.
        # self._call("Runtime.enable")
        # self._call("Page.enable")

        self._evaluate("_C = {}")

    def is_activate(self):
        """ is page activate """
        height = self._evaluate("window.innerHeight")
        hidden = self._evaluate("document.hidden")
        return not hidden and height > 0

    def close(self):
        self._tab.stop()
    
    def _evaluate(self, expression, **kwargs):
        if kwargs:
            d = {}
            for k, v in kwargs.items():
                d[k] = json.dumps(v)
            t = string.Template(expression)
            expression = t.substitute(d)
        return self._call("Runtime.evaluate", expression=expression)

    def _call(self, method, **kwargs):
        logger.debug("call: %s, kwargs: %s", method, kwargs)
        response = self._tab.call_method(method, **kwargs)
        logger.debug("response: %s", response)
        return response.get('result', {}).get('value')

    def current_url(self):
        return self._evaluate("window.location.href")

    def set_current_url(self, url: str):
        return self._evaluate("""(function(url) {
            window.location.href = ${url}
        })""", url=url)

    def find_element_by_xpath(self, xpath: str):
        self._evaluate('''(function(xpath){
            var obj = document.evaluate(xpath, document, null, XPathResult.ANY_TYPE, null);
            var button = obj.iterateNext();
            _C[1] = button;
        })($xpath)
        ''')

    def coord_by_xpath(self, xpath: str):
        coord = self._evaluate('''(function(xpath){
            var obj = document.evaluate(xpath, document, null, XPathResult.ANY_TYPE, null);
            var button = obj.iterateNext();
            var rect = button.getBoundingClientRect()
            // [rect.left, rect.top, rect.right, rect.bottom]
            var x = (rect.left + rect.right)/2
            var y = (rect.top + rect.bottom)/2;
            return JSON.stringify([x, y])
        })(${xpath})''', xpath=xpath)
        return json.loads(coord)
    
    def click(self, x, y, duration=0.2, tap_count=1):
        mills = int(1000*duration) # convert to ms
        self._call("Input.synthesizeTapGesture", x=x, y=y, duration=mills, tapCount=tap_count)


    def click_by_xpath(self, xpath):
        x, y = self.coord_by_xpath(xpath)
        self.click(x, y)

    def clear_text_by_xpath(self, xpath):
        self._evaluate("""(function(xpath){
            var obj = document.evaluate(xpath, document, null, XPathResult.ANY_TYPE, null);
            var button = obj.iterateNext();
            button.value = ""
        })($xpath)""", xpath=xpath)

    def send_keys(self, text):
        """
        Input text

        Refs:
            https://github.com/Tencent/FAutoTest/blob/58766fcb98d135ebb6be88893d10c789a1a50e18/fastAutoTest/core/h5/h5PageOperator.py#L40
            http://compatibility.remotedebug.org/Input/Chrome%20(CDP%201.2)/commands/dispatchKeyEvent
        """
        for c in text:
            self._call("Input.dispatchKeyEvent", type="char", text=c)

    def screenshot(self):
        """ always stuck """
        raise NotImplementedError()


from contextlib import contextmanager

from selenium import webdriver


@contextmanager
def driver(package_name):
    serial = adbutils.adb.device().serial
    capabilities = {
        "androidDeviceSerial": serial,
        "androidPackage": package_name,
        "androidUseRunningApp": True,
    }
    dr = webdriver.Remote("http://localhost:9515", {
        "chromeOptions": capabilities
    })
    try:
        yield dr
    finally:
        dr.quit()

def chromedriver():
    package_name = "io.appium.android.apis"
    package_name = "com.xueqiu.android"

    with driver(package_name) as dr:
        print(dr.current_url)
        elem = dr.find_element_by_xpath('//*[@id="phone-number"]')
        elem.click()
        elem.send_keys("123456")
        #dr.save_screenshot("s.png"


def test_self_driver():
    d = adbutils.adb.device()
    package_name = "com.xueqiu.android"
    # package_name = "io.appium.android.apis"
    d.forward("tcp:7912", "tcp:7912")
    ret = requests.get(f"http://localhost:7912/proc/{package_name}/webview").json()
    for data in ret:
        pprint(data)
        lport = d.forward_port("localabstract:"+data["socketPath"])
        wd = WebviewDriver(f"http://localhost:{lport}")
        tabs = wd.get_active_tab_list()
        pprint(tabs)
        for tab in tabs:
            print(tab.current_url())
            tab.click_by_xpath('//*[@id="phone-number"]')
            tab.clear_text_by_xpath('//*[@id="phone-number"]')
            tab.send_keys("123456789")
        break


def runtest():
    import uiautomator2 as u2

    d = u2.connect_usb()
    pprint(d.request_agent("/webviews").json())
    port = d.adb_device.forward_port("localabstract:chrome_devtools_remote")
    wd = WebviewDriver(f"http://localhost:{port}")
    tabs = wd.get_active_tab_list()
    pprint(tabs)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--test", action="store_true", help="run test_self_driver")
    args = parser.parse_args()

    # WebviewDriver()
    import uiautomator2 as u2

    d = u2.connect_usb()
    assert d.adb_device, "must connect with usb"
    for socket_path in d.request_agent("/webviews").json():
        port = d.adb_device.forward_port("localabstract:"+socket_path)
        data = requests.get(f"http://localhost:{port}/json/version").json()
        import pprint
        pprint.pprint(data)
    

if __name__ == "__main__":
    main()
    # if args.test:
    #     print("---- test ----")
    #     test_self_driver()
    # else:
    #     chromedriver()
