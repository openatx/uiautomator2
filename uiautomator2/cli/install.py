# coding: utf-8
#
# https://github.com/openatx/u2init#rest-api

import re
import time
import requests
import uiautomator2
from logzero import logger
import logging

logger.setLevel(logging.DEBUG)

# def oppo_install(self, apk_url):
#     m = hashlib.md5()
#     m.update(apk_url.encode('utf-8'))
#     key = m.hexdigest()[8:16]
#     dst = "/sdcard/atx-" + key + ".apk"  # 安装包会在安装完后自动删除
#     d = uiautomator2.connect(self._device_url)
#     print(d.info, dst)
#     d.push_url(apk_url, dst)
#     # d.push("/Users/codeskyblue/workdir/atxcrawler/apks/ApiDemos-debug.apk", dst) # For debug
#     with d.session("com.coloros.filemanager") as s:
#         s(text=u"所有文件").click()
#         s(className="android.widget.ListView").scroll.to(textContains=key)
#         s(textContains=key).click()

#         btn_done = d(className="android.widget.Button", text=u"完成")
#         while not btn_done.exists:
#             s(text="继续安装旧版本").click_exists()
#             s(text="无视风险安装").click_exists()
#             s(text="重新安装").click_exists()
#             # 自动清除安装包和残留
#             if s(resourceId=
#                  "com.android.packageinstaller:id/install_confirm_panel"
#                  ).exists:
#                 # 通过偏移点击<安装>
#                 s(resourceId=
#                   "com.android.packageinstaller:id/bottom_button_layout"
#                   ).click(offset=(0.75, 0.5))
#         btn_done.click()

#     def vivo_install(self, apk_url):
#         print("Vivo detected, open u2 watchers")
#         u = uiautomator2.connect_wifi(self._device_url)
#         u.watcher("AUTO_INSTALL").when(
#             textMatches="好|安装", className="android.widget.Button").click()
#         u.watchers.watched = True
#         self.pm_install(apk_url)


def install_apk(device_url, apk_url):
    """
    Args:
        device_url: udid, device_ip or serial(when usb connected)
    """
    psurl = pkgserv_addr(device_url)
    _http_install_apk(psurl, apk_url)


def pkgserv_addr(device_url):
    """
    根据设备线获取到atxserver的地址，然后再获取到u2init的地址，直接再决定是无线安装还是手动安装
    
    Returns:
        Package API url
    """
    logger.info("device url %s", device_url)
    d = uiautomator2.connect(device_url)
    devinfo = d.device_info
    serial = devinfo['serial']
    logger.info("serial %s, udid %s", serial, devinfo['udid'])
    aserver_url = devinfo.get(
        "serverUrl",
        "http://wifiphone.nie.netease.com")  # TODO(atx-agent should udpate)
    logger.info("atx-server url %s", aserver_url)
    r = requests.get(
        aserver_url + "/devices/" + devinfo['udid'] + "/info").json()
    pvd = r.get('provider')
    if not pvd:
        logger.info("u2init not connected")
        return "http://" + d.wlan_ip + ":7912/packages"
    pkg_url = 'http://%s:%d/devices/%s/pkgs' % (pvd['ip'], pvd['port'], serial)
    logger.info("package url %s", pkg_url)
    return pkg_url


def _http_install_apk(pkg_restapi, apk_url):
    """ install apk from u2init """
    resp = requests.post(pkg_restapi, data={"url": apk_url}).json()
    if not resp.get('success'):
        raise RuntimeError(resp.get('description'))

    id = resp['data']['id']
    logger.info("install id %s", id)
    _wait_installed(pkg_restapi + "/" + id)


def _wait_installed(query_url):
    """ query until install finished """
    while True:
        data = safe_getjson(query_url)
        status = data.get('status')
        logger.debug("%s %s", status, data.get('description'))
        if status in ("success", "failure"):
            break
        time.sleep(1)


def safe_getjson(url):
    """ get rest api """
    r = requests.get(url).json()
    desc = r.get('description')
    if not r.get('success'):
        raise RuntimeError(desc)
    return r.get('data')


def main():
    # ins = U2Installer("http://localhost:17000")
    # apk_url = "http://arch.s3.netease.com/hzdev-appci/h35_trunk_RelWithDebInfo_373397.apk"  # 1.8G large apk
    apk_url = "https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk"

    # command line
    # python -m uiautomator2.cli install 10.240.174.43 http://arch.s3.netease.com/hzdev-appci/h35_trunk_RelWithDebInfo_373397.apk -s http://wifiphone.nie.netease.com
    # psurl = pkgserv_addr("3578298f")
    psurl = pkgserv_addr("10.242.163.69")
    install_apk(psurl, apk_url)


if __name__ == '__main__':
    main()
