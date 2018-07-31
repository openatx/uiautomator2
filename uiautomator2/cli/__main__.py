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

"""

import time
import requests
import re
import six
import humanize
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
    total = ret.get('totalSize', 0)
    copied = ret.get('copiedSize', 0)
    total_size = humanize.naturalsize(total, gnu=True)
    copied_size = humanize.naturalsize(copied, gnu=True)
    speed = humanize.naturalsize(
        (copied / (time.time() - start_time)), gnu=True)
    print("Pushing {} / {} [{}B/s]".format(copied_size, total_size, speed))


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

    def _provider_install_url(self):
        if not self._server_url:
            return
        url = reformat_addr(self._server_url)
        dinfo = requests.get(self._server_url + "/devices/" +
                             self.devinfo['udid'] + "/info").json()
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
            return purl
        return self._device_install_url()

    def install(self, apk_url):
        install_url = self._install_url()
        r = requests.post(install_url, data={'url': apk_url})
        print(r.text)
        raise_for_status(r)
        id = r.text.strip()
        u = urllib.parse.urlparse(install_url)
        query_url = u.scheme + "://" + u.netloc + "/install/"
        start = time.time()
        while True:
            time.sleep(1)
            r = requests.get(query_url + id)
            raise_for_status(r)
            ret = r.json()
            status = ret['message']
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
            elif status.startswith("err:"):
                raise RuntimeError(status)
            else:
                print(ret)


def main():
    args = docopt(__doc__, version='u2cli 1.0')
    print(args)
    if args['install']:
        apk_url = args['<url>']
        ins = Installer(args['<ip>'] + ":7912", args['--server'])
        ins.install(apk_url)
        # return
        # print("InstallURL", install_url)
        # install_url = get_install_url(args['<ip>'], args['--server'])
        # # https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk'
        # install_apk(install_url, apk_url)


if __name__ == '__main__':
    main()
