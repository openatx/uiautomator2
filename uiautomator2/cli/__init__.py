# coding: utf-8
#
"""
uiautomator2 cli

Usage:
    u2cli install <ip> <url> [--server=<server>]
    u2cli runyaml [--debug] [--step] <filename>

Options:
    -h --help            show this help message
    -v --version         show version
    -s --server=<server>    atx-server url, eg: http://10.0.0.1:8000
    --serial=<serial>    device serial number
    --debug              set loglevel to DEBUG

"""
# u2cli install <url> [--serial=<serial>]

import time
import requests
import re
import six
import sys
import humanize
import hashlib
from docopt import docopt

import uiautomator2
from uiautomator2.cli import runyaml
from uiautomator2.cli import install

urllib = six.moves.urllib


def _reformat_addr(addr):
    if not re.match(r"^https?://", addr):
        addr = "http://" + addr
    u = urllib.parse.urlparse(addr)
    return u.scheme + "://" + u.netloc


class HTTPError(Exception):
    pass


def raise_for_status(r):
    if r.status_code != 200:
        raise HTTPError(r.text)


__commands = {}


def register_command(func, name=None, args=()):
    name = name or func.__name__
    __commands[name] = (func, args)


def __cmd_install(ip, server, apk_url):
    install.install_apk(ip, apk_url)


def __cmd_runyaml(debug, onlystep, filename):
    try:
        import yaml
    except ImportError:
        sys.exit("you need to install pyaml")
    runyaml.main(filename, debug, onlystep)


def main():
    args = docopt(__doc__, version='u2cli 1.1')
    print(args)
    register_command(__cmd_install, 'install', ('<ip>', '--server', '<url>'))
    register_command(__cmd_runyaml, "runyaml",
                     ('--debug', '--step', '<filename>'))

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
