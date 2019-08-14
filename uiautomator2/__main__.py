# coding: utf-8
#

from __future__ import absolute_import, print_function

import argparse
import hashlib
import logging
import os
import re
import shutil
import tarfile
import json

import humanize
import progress.bar
import requests
from logzero import logger
from retry import retry

import uiautomator2 as u2
from uiautomator2 import adbutils
from uiautomator2.version import __apk_version__, __atx_agent_version__

appdir = os.path.join(os.path.expanduser("~"), '.uiautomator2')
logger.debug("use cache directory: %s", appdir)

GITHUB_BASEURL = "https://github.com/openatx"


class DownloadBar(progress.bar.Bar):
    message = "Downloading"
    suffix = '%(current_size)s / %(total_size)s'

    @property
    def total_size(self):
        return humanize.naturalsize(self.max, gnu=True)

    @property
    def current_size(self):
        return humanize.naturalsize(self.index, gnu=True)


def cache_download(url, filename=None, timeout=None):
    """ return downloaded filepath """
    # check cache
    if not filename:
        filename = os.path.basename(url)
    storepath = os.path.join(appdir,
                             hashlib.sha224(url.encode()).hexdigest(),
                             filename)
    storedir = os.path.dirname(storepath)
    if not os.path.isdir(storedir):
        os.makedirs(storedir)
    if os.path.exists(storepath) and os.path.getsize(storepath) > 0:
        logger.debug("Use cached assets: %s", storepath)
        return storepath

    logger.debug("Download %s", url)
    # download from url
    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        'Connection': 'keep-alive',
        'Origin': 'https://github.com',
        'User-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36'
    } # yapf: disable
    r = requests.get(url, stream=True, headers=headers, timeout=None)
    r.raise_for_status()

    file_size = int(r.headers.get("Content-Length"))
    bar = DownloadBar(filename, max=file_size)
    with open(storepath + '.tmp', 'wb') as f:
        chunk_length = 16 * 1024
        while 1:
            buf = r.raw.read(chunk_length)
            if not buf:
                break
            f.write(buf)
            bar.next(len(buf))
        bar.finish()
    shutil.move(storepath + '.tmp', storepath)
    return storepath


def mirror_download(url, filename: str):
    github_host = "https://github.com"
    if url.startswith(github_host):
        mirror_url = "http://tool.appetizer.io" + url[len(
            github_host):]  # mirror of github
        try:
            return cache_download(mirror_url, filename, timeout=60)
        except requests.RequestException as e:
            logger.debug("download from mirror error, use origin source")

    return cache_download(url, filename)


class Initer():
    def __init__(self, device):
        logger.info(">>> Initial device %s", device)
        d = self._device = device

        self.sdk = d.getprop('ro.build.version.sdk')
        self.abi = d.getprop('ro.product.cpu.abi')
        self.pre = d.getprop('ro.build.version.preview_sdk')
        self.arch = d.getprop('ro.arch')
        self.abis = (d.getprop('ro.product.cpu.abilist').strip()
                     or self.abi).split(",")
        self.server_addr = None

    def shell(self, *args):
        logger.debug("Shell: %s", args)
        return self._device.shell(args)

    @property
    def apk_urls(self):
        for name in ["app-uiautomator.apk", "app-uiautomator-test.apk"]:
            yield "".join([
                GITHUB_BASEURL,
                "/android-uiautomator-server/releases/download/",
                __apk_version__, "/", name
            ])

    @property
    def atx_agent_url(self):
        files = {
            'armeabi-v7a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'arm64-v8a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'armeabi': 'atx-agent_{v}_linux_armv6.tar.gz',
            'x86': 'atx-agent_{v}_linux_386.tar.gz',
        }
        name = None
        for abi in self.abis:
            name = files.get(abi)
            if name:
                break
        if not name:
            raise Exception(
                "arch(%s) need to be supported yet, please report an issue in github"
                % self.abis)
        return GITHUB_BASEURL + '/atx-agent/releases/download/%s/%s' % (
            __atx_agent_version__, name.format(v=__atx_agent_version__))

    @property
    def minicap_urls(self):
        base_url = GITHUB_BASEURL + \
            "/stf-binaries/raw/master/node_modules/minicap-prebuilt/prebuilt/"
        sdk = self.sdk
        yield base_url + self.abi + "/lib/android-" + sdk + "/minicap.so"
        yield base_url + self.abi + "/bin/minicap"

    @property
    def minitouch_url(self):
        return ''.join([
            GITHUB_BASEURL + "/stf-binaries",
            "/raw/master/node_modules/minitouch-prebuilt/prebuilt/",
            self.abi + "/bin/minitouch"
        ])

    def push_url(self, url, dest=None, mode=0o755, tgz=False, extract_name=None):  # yapf: disable
        path = mirror_download(url, os.path.basename(url))
        if tgz:
            tar = tarfile.open(path, 'r:gz')
            path = os.path.join(os.path.dirname(path), extract_name)
            tar.extract(extract_name, os.path.dirname(path))
        if not dest:
            dest = "/data/local/tmp/" + os.path.basename(path)

        logger.debug("Push to %s:0%o", dest, mode)
        self._device.sync.push(path, dest, mode=mode)
        return dest

    def is_apk_outdate(self):
        apk1 = self._device.package_info("com.github.uiautomator")
        if not apk1:
            return True
        if apk1['version_name'] != __apk_version__:
            return True
        if not self._device.package_info("com.github.uiautomator.test"):
            return True
        return False

    def install(self, server_addr=None):
        logger.info("Install minicap, minitouch")
        self.push_url(self.minitouch_url)
        if self.abi == "x86":
            logger.info(
                "abi:x86 seems to be android emulator, skip install minicap")
        elif int(self.sdk) >= 29:
            logger.info("Android Q (sdk:29) has no minicap resource")
        else:
            for url in self.minicap_urls:
                self.push_url(url)

        logger.info(
            "Install com.github.uiautomator, com.github.uiautomator.test")

        if self.is_apk_outdate():
            self.shell("pm", "uninstall", "com.github.uiautomator")
            self.shell("pm", "uninstall", "com.github.uiautomator.test")
            for url in self.apk_urls:
                path = self.push_url(url, mode=0o644)
                self.shell("pm", "install", "-r", "-t", path)
        else:
            logger.info("Already installed com.github.uiautomator apks")

        logger.info("Install atx-agent")
        path = self.push_url(self.atx_agent_url,
                             tgz=True,
                             extract_name="atx-agent")
        args = [path, "server", "-d"]
        if server_addr:
            args.extend(['-t', server_addr])
        self.shell(path, "server", "--stop")
        self.shell(*args)

        logger.info("Check install")
        self.check_atx_agent_version()
        print("Successfully init %s" % self._device)

    @retry(
        (requests.ConnectionError, requests.ReadTimeout, requests.HTTPError),
        delay=.5,
        tries=10)
    def check_atx_agent_version(self):
        port = self._device.forward_port(7912)
        logger.debug("Forward: local:tcp:%d -> remote:tcp:%d", port, 7912)
        response = requests.get("http://127.0.0.1:%d/version" % port).text
        logger.debug("atx-agent version %s", response.strip())


def cmd_init(args):
    if args.serial:
        device = adbutils.adb.device(args.serial)
        init = Initer(device)
        init.install(args.server)

    else:
        for device in adbutils.adb.iter_device():
            init = Initer(device)
            init.install(args.server)


def cmd_screenshot(args):
    d = u2.connect(args.serial)
    d.screenshot().save(args.filename)


def cmd_identify(args):
    d = u2.connect(args.serial)
    d.press("home")
    d.open_identify(args.theme)


def cmd_install(args):
    u = u2.connect(args.serial)
    pkg_name = u.app_install(args.url)
    print("Installed", pkg_name)


def cmd_uninstall(args):
    d = u2.connect(args.serial)
    if args.all:
        d.app_uninstall_all(verbose=True)
    else:
        for package_name in args.package_name:
            print("Uninstall \"%s\" " % package_name, end="", flush=True)
            ok = d.app_uninstall(package_name)
            print("OK" if ok else "FAIL")


def cmd_healthcheck(args):
    d = u2.connect(args.serial)
    d.healthcheck()


def cmd_start(args):
    d = u2.connect(args.serial)
    d.app_start(args.package_name)


def cmd_stop(args):
    d = u2.connect(args.serial)
    if args.all:
        d.app_stop_all()
        return

    for package_name in args.package_name:
        print("am force-stop \"%s\" " % package_name)
        d.app_stop(package_name)


def cmd_current(args):
    d = u2.connect(args.serial)
    print(json.dumps(d.current_app(), indent=4))


_commands = [
    dict(action=cmd_init,
         command="init",
         help="install enssential resources to device",
         flags=[
             dict(args=['--serial', '-s'], type=str, help='serial number'),
             dict(name=['server'], type=str, help='atxserver address'),
             dict(args=['serial'],
                  nargs='?',
                  help='serial number, same as --serial'),
         ]),
    dict(action=cmd_screenshot,
         command="screenshot",
         help="take device screenshot",
         flags=[
             dict(args=['filename'],
                  type=str,
                  help="output filename, jpg or png")
         ]),
    dict(action=cmd_identify,
         command="identify",
         help="quickly find your device by change device screen color",
         flags=[
             dict(args=['--theme'],
                  type=str,
                  default='red',
                  help="black or red")
         ]),
    dict(action=cmd_install,
         command="install",
         help="install packages",
         flags=[
             dict(args=["url"], help="package url"),
         ]),
    dict(action=cmd_uninstall,
         command="uninstall",
         help="uninstall packages",
         flags=[
             dict(args=["--all"],
                  action="store_true",
                  help="uninstall all packages"),
             dict(args=["package_name"], nargs="*", help="package name")
         ]),
    dict(action=cmd_healthcheck,
         command="healthcheck",
         help="recover uiautomator service"),
    dict(action=cmd_healthcheck,
         command="check",
         help="alias of healthcheck"),
    dict(action=cmd_start,
         command="start",
         help="start application",
         flags=[
             dict(args=["package_name"],
                  type=str,
                  nargs=None,
                  help="package name")
         ]),
    dict(action=cmd_stop,
         command="stop",
         help="stop application",
         flags=[
             dict(args=["--all"], action="store_true", help="stop all"),
             dict(args=["package_name"], nargs="*", help="package name")
         ]),
    dict(action=cmd_current,
         command="current",
         help="show current application"),
]


def main():
    # yapf: disable
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--serial', type=str,
                        help='device serial number')

    subparser = parser.add_subparsers(dest='subparser')

    actions = {}
    for c in _commands:
        cmd_name = c['command']
        actions[cmd_name] = c['action']
        sp = subparser.add_parser(cmd_name, help=c.get('help'),
                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        for f in c.get('flags', []):
            args = f.get('args')
            if not args:
                args = ['-'*min(2, len(n)) + n for n in f['name']]
            kwargs = f.copy()
            kwargs.pop('name', None)
            kwargs.pop('args', None)
            sp.add_argument(*args, **kwargs)

    args = parser.parse_args()
    print("DEBUG:", args, args.subparser)

    if args.subparser:
        actions[args.subparser](args)
    return
    # yapf: enable


if __name__ == '__main__':
    # import logzero
    # logzero.loglevel(logging.INFO)
    main()
