# coding: utf-8
#

from __future__ import absolute_import, print_function

import argparse
import hashlib
import logging
import os
import re
import shutil
import sys
import tarfile
import time

import fire
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


def cache_download(url, filename=None):
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
        return storepath
    # download from url
    r = requests.get(url, stream=True)
    if r.status_code != 200:
        raise Exception(url, "status code", r.status_code)
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
        return self._device.shell_output(*args)

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
                % abis)
        return GITHUB_BASEURL + '/atx-agent/releases/download/%s/%s' % (
            __atx_agent_version__, name.format(v=__atx_agent_version__))

    @property
    def minicap_urls(self):
        base_url = GITHUB_BASEURL + \
            "/stf-binaries/raw/master/node_modules/minicap-prebuilt/prebuilt/"
        sdk = self.sdk
        if self.pre and self.pre != "0":
            sdk = sdk + self.pre
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
        path = cache_download(url, os.path.basename(url))
        if tgz:
            tar = tarfile.open(path, 'r:gz')
            path = os.path.join(os.path.dirname(path), extract_name)
            tar.extract(extract_name, os.path.dirname(path))
        if not dest:
            dest = "/data/local/tmp/" + os.path.basename(path)

        logger.debug("Push %s -> %s:0%o", url, dest, mode)
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
        path = self.push_url(
            self.atx_agent_url, tgz=True, extract_name="atx-agent")
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

    # def check_apk_installed(self, apk_version):
    #     """ in OPPO device, if you check immediatelly, package_info will return None """
    #     pkg_info = self.package_info("com.github.uiautomator")
    #     if not pkg_info:
    #         raise EnvironmentError(
    #             "package com.github.uiautomator not installed")
    #     if pkg_info['version_name'] != apk_version:
    #         raise EnvironmentError(
    #             "package com.github.uiautomator version expect \"%s\" got \"%s\""
    #             % (apk_version, pkg_info['version_name']))

    #             r = requests.get(
    #                 'http://localhost:%d/version' % lport, timeout=10)
    #             r.raise_for_status()
    #             log.info("atx-agent version: %s", r.text)
    #             # todo finish the retry logic
    #             print("atx-agent output:", output.strip())
    #             # open uiautomator2 github URL
    #             self.shell("am", "start", "-a", "android.intent.action.VIEW",
    #                        "-d", "https://github.com/openatx/uiautomator2")


class MyFire(object):
    def update_apk(self, ip):
        """ update com.github.uiautomator apk remotely """
        u = u2.connect(ip)
        apk_version = __apk_version__
        app_url = GITHUB_BASEURL + \
            '/android-uiautomator-server/releases/download/%s/app-uiautomator.apk' % apk_version
        app_test_url = GITHUB_BASEURL + \
            '/android-uiautomator-server/releases/download/%s/app-uiautomator-test.apk' % apk_version
        u.app_install(app_url)
        u.app_install(app_test_url)

    def clear_cache(self):
        logger.info("clear cache dir: %s", appdir)
        shutil.rmtree(appdir, ignore_errors=True)

    def install(self, arg1, arg2=None):
        """
        Example:
            install "http://some-host.apk"
            install "$serial" "http://some-host.apk"
        """
        if arg2 is None:
            device_ip, apk_url = None, arg1
        else:
            device_ip, apk_url = arg1, arg2
        u = u2.connect(device_ip)
        pkg_name = u.app_install(apk_url)
        print("Installed", pkg_name)

    def unlock(self, device_ip=None):
        u = u2.connect(device_ip)
        u.unlock()

    def app_stop_all(self, device_ip=None):
        u = u2.connect(device_ip)
        u.app_stop_all()

    def uninstall_all(self, device_ip=None):
        u = u2.connect(device_ip)
        u.app_uninstall_all(verbose=True)

    def identify(self, device_ip=None, theme='black'):
        u = u2.connect(device_ip)
        u.open_identify(theme)

    def screenshot(self, device_ip, filename):
        u = u2.connect(device_ip)
        u.screenshot(filename)

    def healthcheck(self, device_ip):
        u = u2.connect(device_ip)
        u.healthcheck()


def cmd_init(args):
    if args.serial:
        device = adbutils.adb.device_with_serial(args.serial)
        init = Initer(device)
        init.install(args.server)

    else:
        for device in adbutils.adb.iter_device():
            init = Initer(device)
            init.install(args.server)


_commands = [{
    "command": "init",
    "help": "install enssential resources to device",
    "flags": [
        dict(
            args=['--serial', '-s'],
            type=str,
            help='serial number'),
        dict(
            name=['server'],
            type=str,
            help='atx-server address')
    ],
    "action": cmd_init,
}]  # yapf: disable


def main():
    # yapf: disable
    if len(sys.argv) >= 2 and sys.argv[1] in ('init',):
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
        print(args, args.subparser)

        if args.subparser:
            actions[args.subparser](args)
        return
    # yapf: enable

    fire.Fire(MyFire)


if __name__ == '__main__':
    # import logzero
    # logzero.loglevel(logging.INFO)
    main()
