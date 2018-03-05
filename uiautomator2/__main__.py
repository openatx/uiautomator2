# coding: utf-8
#

from __future__ import print_function
from __future__ import absolute_import

import fire
import os
import logging
import subprocess
import shutil
import tarfile
import hashlib
import re
import time
import socket
import progress.bar
from contextlib import closing

import humanize
import requests

import uiautomator2 as u2
from uiautomator2 import adbutils
from uiautomator2.version import __apk_version__, __atx_agent_version__



def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

log = get_logger('uiautomator2')
appdir = os.path.join(os.path.expanduser("~"), '.uiautomator2')
log.debug("use cache directory: %s", appdir)


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
    storepath = os.path.join(appdir, hashlib.sha224(url.encode()).hexdigest(), filename)
    storedir = os.path.dirname(storepath)
    if not os.path.isdir(storedir):
        os.makedirs(storedir)
    if os.path.exists(storepath) and os.path.getsize(storepath) > 0:
        log.debug("file '%s' cached before", filename)
        return storepath
    # download from url
    r = requests.get(url, stream=True)
    log.debug("download from %s", url)
    if r.status_code != 200:
        raise Exception("status code", r.status_code)
    file_size = int(r.headers.get("Content-Length"))
    bar = DownloadBar(filename, max=file_size)
    with open(storepath+'.tmp', 'wb') as f:
        chunk_length = 16*1024
        while 1:
            buf = r.raw.read(chunk_length)
            if not buf:
                break
            f.write(buf)
            bar.next(len(buf))
        bar.finish()
    shutil.move(storepath+'.tmp', storepath)
    return storepath


class Installer(adbutils.Adb):
    def __init__(self, serial=None):
        super(Installer, self).__init__(serial)
        self.sdk = self.getprop('ro.build.version.sdk')
        self.abi = self.getprop('ro.product.cpu.abi')
        self.pre = self.getprop('ro.build.version.preview_sdk')
        self.arch = self.getprop('ro.arch')
        self.server_addr = None

    def install_minicap(self):
        if self.arch == 'x86':
            log.info("skip install minicap on emulator")
            return
        sdk = self.sdk
        if self.pre and self.pre != "0":
            sdk = sdk + self.pre
        base_url = "https://github.com/codeskyblue/stf-binaries/raw/master/node_modules/minicap-prebuilt/prebuilt/"
        log.debug("install minicap.so")
        url = base_url+self.abi+"/lib/android-"+sdk+"/minicap.so"
        path = cache_download(url)
        self.push(path, '/data/local/tmp/minicap.so')
        log.info("install minicap")
        url = base_url+self.abi+"/bin/minicap"
        path = cache_download(url)
        self.push(path, '/data/local/tmp/minicap', 0o755)

    def install_minitouch(self):
        """ Need test """
        log.info("install minitouch")
        url = ''.join(["https://github.com/codeskyblue/stf-binaries",
            "/raw/master/node_modules/minitouch-prebuilt/prebuilt/",
            self.abi+"/bin/minitouch"])
        path = cache_download(url)
        self.push(path, '/data/local/tmp/minitouch', 0o755)
    
    def install_uiautomator_apk(self, apk_version, reinstall=False):
        app_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator.apk' % apk_version
        app_test_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator-test.apk' % apk_version
        pkg_info = self.package_info('com.github.uiautomator')
        test_pkg_info = self.package_info('com.github.uiautomator.test')
        # For test_pkg_info has no versionName or versionCode
        # Just check if the com.github.uiautomator.test apk is installed
        if not reinstall and pkg_info and pkg_info['version_name'] == apk_version and test_pkg_info:
            log.info("apk(%s) already installed, skip", apk_version)
            return
        if pkg_info or test_pkg_info:
            log.debug("uninstall old apks")
            self.uninstall('com.github.uiautomator')
            self.uninstall('com.github.uiautomator.test')
        log.info("app-uiautomator.apk(%s) installing ...", apk_version)
        path = cache_download(app_url)
        self.install(path)
        log.debug("app-uiautomator.apk installed")

        log.info("app-uiautomator-test.apk installing ...")
        path = cache_download(app_test_url)
        self.install(path)
        log.debug("app-uiautomator-test.apk installed")
    
    def check_apk_installed(self, apk_version):
        """ in OPPO device, if you check immediatelly, package_info will return None """
        pkg_info = self.package_info("com.github.uiautomator")
        if not pkg_info:
            raise EnvironmentError("package com.github.uiautomator not installed")
        if pkg_info['version_name'] != apk_version:
            raise EnvironmentError("package com.github.uiautomator version expect \"%s\" got \"%s\"" % (apk_version, pkg_info['version_name']))
        # test apk
        pkg_test_info = self.package_info("com.github.uiautomator.test")
        if not pkg_test_info:
            raise EnvironmentError("package com.github.uiautomator.test not installed")

    
    def install_atx_agent(self, agent_version, reinstall=False):
        version_output = self.shell('/data/local/tmp/atx-agent', '-v', raise_error=False).strip()
        m = re.search(r"\d+\.\d+\.\d+", version_output)
        current_agent_version = m.group(0) if m else None
        if current_agent_version == agent_version:
            log.info("atx-agent(%s) already installed, skip", agent_version)
            return
        if current_agent_version == 'dev' and not reinstall:
            log.warn("atx-agent develop version, skip")
            return
        if current_agent_version:
            log.info("atx-agent(%s) need to update", current_agent_version)
        files = {
            'armeabi-v7a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'arm64-v8a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'armeabi': 'atx-agent_{v}_linux_armv6.tar.gz',
            'x86': 'atx-agent_{v}_linux_386.tar.gz',
        }
        log.info("atx-agent(%s) is installing, please be patient", agent_version)
        abis = self.shell('getprop', 'ro.product.cpu.abilist').strip() or self.abi
        name = None
        for abi in abis.split(','):
            name = files.get(abi)
            if name:
                break
        if not name:
            raise Exception("arch(%s) need to be supported yet, please report an issue in github" % abis)
        url = 'https://github.com/openatx/atx-agent/releases/download/%s/%s' % (
            agent_version,
            name.format(v=agent_version))
        log.debug("download atx-agent(%s) from github releases", agent_version)
        path = cache_download(url)
        tar = tarfile.open(path, 'r:gz')
        bin_path = os.path.join(os.path.dirname(path), 'atx-agent')
        tar.extract('atx-agent', os.path.dirname(bin_path))
        self.push(bin_path, '/data/local/tmp/atx-agent', 0o755)
        log.debug("atx-agent installed")

    def launch_and_check(self):
        log.info("launch atx-agent daemon")
        args = ['TMPDIR=/sdcard', '/data/local/tmp/atx-agent', '-d']
        if self.server_addr:
            args.append('-t')
            args.append(self.server_addr)
        output = self.shell(*args)
        lport = self.forward_port(7912)
        log.debug("forward device(port:7912) -> %d", lport)
        time.sleep(.5)
        cnt = 0
        while cnt < 3:
            try:
                r = requests.get('http://localhost:%d/version' % lport, timeout=3)
                log.debug("atx-agent version: %s", r.text)
                # todo finish the retry logic
                log.info("atx-agent output: %s", output.strip())
                # open uiautomator2 github URL
                self.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", "https://github.com/openatx/uiautomator2")
                log.info("success")
                break
            except requests.exceptions.ConnectionError:
                time.sleep(.5)
                cnt += 1
        else:
            log.error("failure")


class MyFire(object):
    def init(self, server=None, apk_version=__apk_version__, agent_version=__atx_agent_version__, verbose=False, reinstall=False, proxy=None, serial=None):
        if verbose:
            log.setLevel(logging.DEBUG)
        if server:
            log.info("atx-server addr %s", server)

        if proxy:
            os.environ['HTTP_PROXY'] = proxy
            os.environ['HTTPS_PROXY'] = proxy

        if not serial:
            output = subprocess.check_output(['adb', 'devices'])
            pattern = re.compile(r'(?P<serial>[^\s]+)\t(?P<status>device|offline)')
            matches = pattern.findall(output.decode())
            valid_serials = [m[0] for m in matches if m[1] == 'device']
            if len(valid_serials) == 0:
                log.warning("No avaliable android devices detected.")
                return
            if len(valid_serials) > 1:
                log.warning("More then 1 device detected, you must specify android serial")
                return
            serial = valid_serials[0]
        
        log.info("Device(%s) initialing ...", serial)
        ins = Installer(serial)
        ins.server_addr = server
        ins.install_minicap()
        ins.install_minitouch()
        ins.install_uiautomator_apk(apk_version, reinstall)
        ins.install_atx_agent(agent_version, reinstall)
        ins.check_apk_installed(apk_version)
        ins.launch_and_check()

    def clear_cache(self):
        log.info("clear cache dir: %s", appdir)
        shutil.rmtree(appdir, ignore_errors=True)
    
    def cleanup(self):
        raise NotImplementedError()

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
    
    def upgrade_apk(self, device_ip):
        """ update com.github.uiautomator apk remotely """
        app_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator.apk' % __apk_version__
        app_test_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator-test.apk' % __apk_version__
        u = u2.connect(device_ip)
        u.app_install(app_url)
        u.app_install(app_test_url)


def main():
    fire.Fire(MyFire)


if __name__ == '__main__':
    main()
    
