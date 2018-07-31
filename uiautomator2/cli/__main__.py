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
from docopt import docopt

urllib = six.moves.urllib


def reformat_addr(addr):
    if not re.match(r"^https?://", addr):
        addr = "http://" + addr
    u = urllib.parse.urlparse(addr)
    return u.scheme + "://" + u.netloc


def get_install_url(ip, server=None):
    """
    Args:
        ip: device ip, eg 10.0.0.2
        server: atx-server addr eg 10.1.1.1:8000
    """
    default_url = 'http://' + ip + ":7912/install"
    if not server:
        return default_url
    try:
        server_url = reformat_addr(server)
        r = requests.get(server_url + "/devices/ip:" + ip + "/info", timeout=2)
        raise_for_status(r)
        dinfo = r.json()
        provider = dinfo.get('provider')
        if not provider:
            return default_url
        return 'http://{}:{}/install/{}'.format(
            provider['ip'], provider['port'], dinfo['serial'])
    except Exception as e:
        print("ERR(get install url):", str(e))
        return default_url


class HTTPError(Exception):
    pass


def raise_for_status(r):
    if r.status_code != 200:
        raise HTTPError(r.text)


def install_apk(install_url, apk_url):
    r = requests.post(install_url, data={'url': apk_url})
    print(r.text)
    raise_for_status(r)
    id = r.text.strip()
    u = urllib.parse.urlparse(install_url)
    query_url = u.scheme + "://" + u.netloc + "/install/"
    while True:
        time.sleep(1)
        r = requests.get(query_url + id)
        raise_for_status(r)
        ret = r.json()
        status = ret['message']
        if status == 'finished':
            print("Success installed")
            return True
        elif status.startswith("err:"):
            raise RuntimeError(status)
        else:
            print(ret)


def main():
    args = docopt(__doc__, version='u2cli 1.0')
    print(args)
    if args['install']:
        install_url = get_install_url(args['<ip>'], args['--server'])
        print("InstallURL", install_url)
        # https://gohttp.nie.netease.com/tools/apks/qrcodescan-2.6.0-green.apk'
        apk_url = args['<url>']
        install_apk(install_url, apk_url)


if __name__ == '__main__':
    main()