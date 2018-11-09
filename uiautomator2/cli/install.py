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


def oppo_install(self, apk_url):
    m = hashlib.md5()
    m.update(apk_url.encode('utf-8'))
    key = m.hexdigest()[8:16]
    dst = "/sdcard/atx-" + key + ".apk"  # 安装包会在安装完后自动删除
    d = uiautomator2.connect(self._device_url)
    print(d.info, dst)
    d.push_url(apk_url, dst)
    # d.push("/Users/codeskyblue/workdir/atxcrawler/apks/ApiDemos-debug.apk", dst) # For debug
    with d.session("com.coloros.filemanager") as s:
        s(text=u"所有文件").click()
        s(className="android.widget.ListView").scroll.to(textContains=key)
        s(textContains=key).click()

        btn_done = d(className="android.widget.Button", text=u"完成")
        while not btn_done.exists:
            s(text="继续安装旧版本").click_exists()
            s(text="无视风险安装").click_exists()
            s(text="重新安装").click_exists()
            # 自动清除安装包和残留
            if s(resourceId=
                 "com.android.packageinstaller:id/install_confirm_panel"
                 ).exists:
                # 通过偏移点击<安装>
                s(resourceId=
                  "com.android.packageinstaller:id/bottom_button_layout"
                  ).click(offset=(0.75, 0.5))
        btn_done.click()


def getu2init(atxserver, udid):
    r = requests.get(atxserver + "/devices/" + udid + "/info").json()
    ip = r.get("provider").get("ip")
    port = r.get('provider').get('port')
    addr = 'http://%s:%d' % (ip, port)
    return addr, r.get('serial')


class U2Installer(object):
    def __init__(self, u2server):
        """
        Args:
            u2server (str): u2init url
        """
        u2server = u2server.rstrip("/")
        if not re.match(r"https?://", u2server):
            u2server = "http://" + u2server
        self._u2server = u2server

    def _urlfor(self, url_format, *args):
        suburl = url_format % args
        return self._u2server + suburl

    def _getjson(self, url):
        r = requests.get(url).json()
        if not r.get('success'):
            raise RuntimeError(r.get('description'))
        return r.get('data'), r.get('description')

    def _devinfo(self, serial):
        """
        Returns example:
        {
            "agentPort": 61907,
            "model": "OD103",
            "product": "odin",
            "serial": "3578298f",
            "udid": "3578298f-b4:0b:44:e6:1f:90-OD103"
        }
        """
        data, _ = self._getjson(self._urlfor("/devices/%s/info", serial))
        return data

    def connect(self, serial):
        """
        return uiautomator2 instance
        """
        port = self._devinfo(serial)['agentPort']
        # generate u2 connect url
        device_url = self._u2server + ":" + str(port)
        if not re.match(r":\d+$", self._u2server):
            device_url = re.sub(r"\d+$", str(port), self._u2server)
        print(device_url)
        d = uiautomator2.connect(device_url)
        s = d.session()

    def install_apk(self, serial, apk_url):
        """ install through url """
        r = requests.post(
            self._urlfor("/devices/%s/pkgs", serial), data={
                "url": apk_url
            }).json()
        desc = r.get('description')
        if not r.get("success"):
            raise RuntimeError(desc)
        id = r.get('data').get('id')
        print("install id", id)
        self._wait_installed(self._urlfor("/devices/%s/pkgs/%s", serial, id))

    def _wait_installed(self, query_url):
        while True:
            data, _ = self._getjson(query_url)
            status = data.get('status')
            # message = '{} {}'.format(status, data.get('description'))
            print("[%s] %s %s" % (time.strftime("%H:%M:%S"), status,
                                  data.get("description")))
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


def pkgserv_addr(device_url):
    """
    根据设备线获取到atxserver的地址，然后再获取到u2init的地址，直接再决定是无线安装还是手动安装
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
        return
    pkg_url = 'http://%s:%d/devices/%s/pkgs' % (pvd['ip'], pvd['port'], serial)
    logger.info("package url %s", pkg_url)
    return pkg_url


def u2init_install_apk(pkg_url, apk_url):
    """ install apk from u2init """
    resp = requests.post(pkg_url, data={"url": apk_url}).json()
    if not resp.get('success'):
        raise RuntimeError(resp.get('description'))

    id = resp['data']['id']
    logger.info("install id %s", id)
    _wait_installed(pkg_url + "/" + id)


def _wait_installed(query_url):
    """ query until install finished """
    while True:
        data = safe_getjson(query_url)
        status = data.get('status')
        logger.debug("%s %s", status, data.get('description'))
        if status in ("success", "failure"):
            break
        time.sleep(1)


def install_apk(u2init_url, serial, apk_url):
    """
    Args:
        u2init_url (str): eg: http://localhost:17000
        serial (str): android device serial
        apk_url (str): android apk url
    
    Raises:
        RuntimeError
    """

    if not re.match(r"^https?://", u2init_url):
        u2init_url = "http://" + u2init_url
    pkgs_url = "{}/devices/{}/pkgs".format(u2init_url, serial)

    r = requests.get("%s/devices/%s/info" % (u2init_url, serial)).json()
    if not r.get('success'):
        raise RuntimeError(r.get('description'))

    # post create download id
    r = requests.post(
        pkgs_url, data={
            "url": apk_url,
        }).json()
    if not r.get('success'):
        raise RuntimeError(r.get('description'))
    id = r.get('data').get('id')

    while True:
        r = requests.get(pkgs_url + "/" + id).json()
        if not r.get('success'):
            raise RuntimeError(r.get('description'))
        v = r.get('data')
        status = v['status']
        print("[%s] %s %s" % (time.strftime("%H:%M:%S"), status,
                              v['description']))
        if status == 'installing':
            print("Install callback called")
        if status in ['success', 'failure']:
            break
        time.sleep(1)


# install_apk(
#     "http://10.240.169.31:17000", "3578298f",
#     "https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk")


def main():
    ins = U2Installer("http://localhost:17000")
    apk_url = "https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk"
    # ins.connect("3578298f")
    # lg = "http://arch.s3.netease.com/hzdev-appci/h35_trunk_RelWithDebInfo_373397.apk"
    # ins.install_apk("3578298f", lg)
    # install_apk(
    #     "http://10.240.169.31:17000", "6df1d414",
    #     "https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk")

    # u2initaddr, serial = getu2init("http://wifiphone.nie.netease.com",
    #                                "3578298f-b4:0b:44:e6:1f:90-OD103")
    # print(u2initaddr, serial)
    psurl = pkgserv_addr("3578298f")
    u2init_install_apk(psurl, apk_url)


if __name__ == '__main__':
    main()
