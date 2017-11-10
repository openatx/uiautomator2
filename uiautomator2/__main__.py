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


__apk_version__ = '1.0.5'
__atx_agent_version__ = '0.0.9'


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
        return humanize.naturalsize(self.max, binary=True)
    
    @property
    def current_size(self):
        return humanize.naturalsize(self.index, binary=True)


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
        self.server_addr = None

    def install_minicap(self):
        sdk = self.sdk
        if self.pre and self.pre != "0":
            sdk = sdk + self.pre
        minicap_base_url = "https://github.com/codeskyblue/stf-binaries/raw/master/node_modules/minicap-prebuilt/prebuilt/"
        log.debug("install minicap.so")
        url = minicap_base_url+self.abi+"/lib/android-"+sdk+"/minicap.so"
        path = cache_download(url)
        self.push(path, '/data/local/tmp/minicap.so')
        log.debug("install minicap")
        url = minicap_base_url+self.abi+"/bin/minicap"
        path = cache_download(url)
        self.push(path, '/data/local/tmp/minicap', 0o755)
    
    def install_uiautomator_apk(self, apk_version):
        app_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator.apk' % apk_version
        app_test_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator-test.apk' % apk_version
        pkg_info = self.package_info('com.github.uiautomator')
        test_pkg_info = self.package_info('com.github.uiautomator.test')
        if pkg_info and pkg_info['version_name'] == apk_version:
            log.info("apk already installed, skip")
            return
        if pkg_info or test_pkg_info:
            log.debug("uninstall old apks")
            self.uninstall('com.github.uiautomator')
            self.uninstall('com.github.uiautomator.test')
        log.info("app-uiautomator.apk installing ...")
        path = cache_download(app_url)
        self.install(path)
        log.debug("app-uiautomator.apk installed")
        log.debug("app-uiautomator-test.apk installing ...")
        path = cache_download(app_test_url)
        self.install(path)
        log.debug("app-uiautomator-test.apk installed")
    
    def install_atx_agent(self, agent_version, reinstall=False):
        log.info("atx-agent is installing, please be patient")
        current_agent_version = self.shell('/data/local/tmp/atx-agent', '-v', raise_error=False).strip()
        if current_agent_version == agent_version:
            log.info("atx-agent already installed, skip")
            return
        if current_agent_version == 'dev' and not reinstall:
            log.warn("atx-agent develop version, skip")
            return
        files = {
            'armeabi-v7a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'arm64-v8a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'armeabi': 'atx-agent_{v}_linux_armv6.tar.gz',
        }
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
        log.debug("launch atx-agent daemon")
        args = ['/data/local/tmp/atx-agent', '-d']
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
                log.info("success")
                break
            except requests.exceptions.ConnectionError:
                time.sleep(1.0)
                cnt += 1
        else:
            log.error("failure")


class MyFire(object):
    def init(self, server=None, apk_version=__apk_version__, agent_version=__atx_agent_version__, verbose=False, reinstall=False):
        if verbose:
            log.setLevel(logging.DEBUG)

        output = subprocess.check_output(['adb', 'devices'])
        pattern = re.compile(r'(?P<serial>[\w\d-]+)\t(?P<status>device|offline)')
        matches = pattern.findall(output.decode())
        for m in matches:
            serial, status = m[0], m[1]
            if status == 'offline':
                log.warn("device(%s) is offline, skip", serial)
                continue
            
            log.info("Device(%s) initialing ...", serial)
            ins = Installer(serial)
            ins.server_addr = server
            ins.install_minicap()
            ins.install_uiautomator_apk(apk_version)
            ins.install_atx_agent(agent_version, reinstall)
            ins.launch_and_check()
        if len(matches) == 0:
            log.warn("No avaliable android devices detected. See details from `adb devices`")
        
    def clear_cache(self):
        log.info("clear cache dir: %s", appdir)
        shutil.rmtree(appdir, ignore_errors=True)

    def install(self, device_ip, apk_url):
        """
        Args:
            device_ip (str): "" means local device
        """
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


def main():
    fire.Fire(MyFire)


if __name__ == '__main__':
    main()
    