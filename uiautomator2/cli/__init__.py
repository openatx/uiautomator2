# coding: utf-8
#
"""
uiautomator2 cli

Usage:
    u2cli install <ip> <url> [--server=<server>]

Options:
    -h --help            show this help message
    -v --version         show version
    -s --server=<server>    atx-server url, eg: http://10.0.0.1:8000
    --serial=<serial>    device serial number

"""
#u2cli install <url> [--serial=<serial>]

import time
import requests
import re
import six
import humanize
import uiautomator2
from docopt import docopt

urllib = six.moves.urllib


def reformat_addr(addr):
    if not re.match(r"^https?://", addr):
        addr = "http://" + addr
    u = urllib.parse.urlparse(addr)
    return u.scheme + "://" + u.netloc


class HTTPError(Exception):
    pass


def raise_for_status(r):
    if r.status_code != 200:
        raise HTTPError(r.text)


def show_pushing_progress(ret, start_time):
    """
    Args:
        ret: json message from URL(/install/:id)
    """
    if ret is None:
        print("No progress")
        return
    total = ret.get('totalSize', 0)
    if total == 0:
        print("Total size 0")
        return
    copied = ret.get('copiedSize', 0)
    total_size = humanize.naturalsize(total, gnu=True)
    copied_size = humanize.naturalsize(copied, gnu=True)
    speed = humanize.naturalsize(
        (copied / (time.time() - start_time)), gnu=True)
    progress = 100.0 * float(copied) / float(total)
    print("Pushing {:.1f}% {} / {} [{}B/s]".format(progress, copied_size,
                                                   total_size, speed))


class Installer(object):
    def __init__(self, device_url, server_url):
        self._device_url = reformat_addr(device_url)
        self._server_url = server_url
        self._devinfo = None

    @property
    def devinfo(self):
        if self._devinfo:
            return self._devinfo
        self._devinfo = requests.get(self._device_url + "/info").json()
        return self._devinfo

    @property
    def serial(self):
        return self.devinfo['serial']

    def prepare(self):
        if self.devinfo.get('brand', '').lower() == 'vivo':
            print("Vivo detected, open u2 watchers")
            u = uiautomator2.connect_wifi(self._device_url)
            u.watcher("AUTO_INSTALL").when(
                textMatches="好|安装", className="android.widget.Button").click()
            u.watchers.watched = True

    def install(self, apk_url):
        self.prepare()

        install_url = self._install_url()
        r = requests.post(install_url, data={'url': apk_url})
        print(r.text)
        raise_for_status(r)
        id = r.text.strip()
        u = urllib.parse.urlparse(install_url)
        query_url = u.scheme + "://" + u.netloc + "/install/" + id
        try:
            self._wait_finish(query_url)
        except KeyboardInterrupt:
            print("Catch Interrupt signal, cancel download")
            r = requests.delete(query_url)
            print(r.text)

    def _provider_install_url(self):
        if not self._server_url:
            return
        server_url = reformat_addr(self._server_url)
        dinfo = requests.get(
            server_url + "/devices/" + self.devinfo['udid'] + "/info").json()
        provider = dinfo.get('provider')
        if not provider:
            return None
        return 'http://{}:{}/install/{}'.format(
            provider['ip'], provider['port'], dinfo['serial'])

    def _device_install_url(self):
        return self._device_url + "/install"

    def _install_url(self):
        purl = self._provider_install_url()
        if purl:
            print("Use provider install service:", purl)
            return purl
        iurl = self._device_install_url()
        print("Use device install service:", iurl)
        return iurl

    def _wait_finish(self, query_url):
        start = time.time()
        while True:
            time.sleep(1)
            r = requests.get(query_url)
            raise_for_status(r)
            ret = r.json()
            if not ret:
                print("wait progress info")
                continue
            # raise when error found
            err = ret.get('error')
            if err:
                print("Unexpected error:", err)
                raise RuntimeError(err)
            # message is also status
            status = ret.get('message', '')
            if status == 'finished':
                print("Success installed")
                return True
            elif status == 'pushing':
                show_pushing_progress(ret, start)
            elif status == 'downloading':  # for old style
                show_pushing_progress(ret.get('progress', {}), start)
            elif status == 'installing':
                print("Installing ..")
            elif status == 'success installed':
                print("Installed")
                return
            elif status and status.startswith("err:"):
                raise RuntimeError(status, ret)
            elif status and 'error' in status:
                raise RuntimeError(status, ret)
            else:
                print(ret)


__commands = {}


def register_command(func, name=None, args=()):
    name = name or func.__name__
    __commands[name] = (func, args)


def __cmd_install(ip, server, apk_url):
    print("CMD:", ip, server, apk_url)
    device_url = ip + ":7912"
    ins = Installer(device_url, server)
    ins.install(apk_url)


def main():
    args = docopt(__doc__, version='u2cli 1.0')
    print(args)
    register_command(__cmd_install, 'install', ('<ip>', '--server', '<url>'))

    for cmdname, cmdopts in __commands.items():
        if args[cmdname]:
            func, argnames = cmdopts
            cmdargs = [args[argname] for argname in argnames]
            func(*cmdargs)

        # return
        # print("InstallURL", install_url)
        # install_url = get_install_url(args['<ip>'], args['--server'])
        # # https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk'
        # install_apk(install_url, apk_url)
