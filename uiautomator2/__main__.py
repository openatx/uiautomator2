# coding: utf-8
#

from __future__ import print_function

import os
import logging
import subprocess
import tarfile
import hashlib
import re
import time

import requests

__apk_version = '1.0.4'
__atx_agent_version = '0.0.3'

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

log = get_logger('uiautomator2')
appdir = os.path.join(os.path.expanduser("~"), '.uiautomator2')
log.info("use cache directory: %s", appdir)

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
        log.info("file '%s' cached before", filename)
        return storepath
    # download from url
    r = requests.get(url)
    log.info("download from %s", url)
    if r.status_code != 200:
        raise Exception("status code", r.status_code)
    with open(storepath, 'wb') as f:
        f.write(r.content)
    return storepath


class Adb(object):
    def __init__(self, serial=None):
        self.serial=None
    
    def execute(self, *args):
        cmds = ['adb', '-s', self.serial] if self.serial else ['adb']
        cmds.extend(args)
        cmdline = subprocess.list2cmdline(map(str, cmds))
        return subprocess.check_output(cmdline, stderr=subprocess.STDOUT, shell=True).decode('utf-8')

    def getprop(self, prop):
        return self.execute('shell', 'getprop', prop).strip()

    def push(self, src, dst, mode=0644):
        self.execute('push', src, dst)
        if mode != 0644:
            self.execute('chmod', oct(mode), dst)
    
    def install(self, apk_path):
        sdk = self.getprop('ro.build.version.sdk')
        if int(sdk) <= 23:
            self.execute('install', '-d', '-r', apk_path)
        else:
            self.execute('install', '-d', '-r', '-g', apk_path)


class Installer(Adb):
    def __init__(self, serial=None):
        super(self).__init__(serial)
        self.sdk = self.getprop('ro.build.version.sdk')
        self.abi = self.getprop('ro.product.cpu.abi')
        self.pre = self.getprop('ro.build.version.preview_sdk')

    def install_minicap(self):
        pass
        # TODO


def adb(*args):
    cmds = ['adb']
    cmds.extend(args)
    cmdline = subprocess.list2cmdline(map(str, cmds))
    return subprocess.check_output(cmdline, stderr=subprocess.STDOUT, shell=True).decode('utf-8')


def adb_install(path):
    sdk = adb('shell', 'getprop', 'ro.build.version.sdk').strip()
    if int(sdk) <= 23:
        adb('install', '-d', '-r', path)
    else:
        adb('install', '-d', '-r', '-g', path)


def adb_package_info(pkg_name):
    output = adb('shell', 'dumpsys', 'package', pkg_name)
    m = re.compile(r'versionName=(?P<name>[\d.]+)').search(output)
    if m:
        return dict(version_name=m.group('name'))


def install_minicap(abi, sdk, pre):
    if pre and pre != "0":
        sdk = sdk + pre
    minicap_base_url = "https://github.com/codeskyblue/stf-binaries/raw/master/node_modules/minicap-prebuilt/prebuilt/"
    log.info("install minicap.so")
    url = minicap_base_url+abi+"/lib/android-"+sdk+"/minicap.so"
    path = cache_download(url)
    adb('push', path, '/data/local/tmp/minicap.so')
    log.info("install minicap")
    url = minicap_base_url+abi+"/bin/minicap"
    path = cache_download(url)
    adb('push', path, '/data/local/tmp/minicap')
    adb('shell', 'chmod', '0755', '/data/local/tmp/minicap')


def install_uiautomator_apk(sdk):
    app_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator.apk' % __apk_version
    app_test_url = 'https://github.com/openatx/android-uiautomator-server/releases/download/%s/app-uiautomator-test.apk' % __apk_version
    pkg_info = adb_package_info('com.github.uiautomator')
    if pkg_info and pkg_info['version_name'] == __apk_version:
        log.info("apk already installed, skip")
        return
    log.info("app-uiautomator.apk installing ...")
    path = cache_download(app_url)
    adb_install(path)
    log.info("app-uiautomator.apk installed")
    log.info("app-uiautomator-test.apk installing ...")
    path = cache_download(app_test_url)
    adb_install(path)
    log.info("app-uiautomator-test.apk installed")


def install_atx_agent():
    log.info("install atx-agent")
    files = {
        'armeabi-v7a': 'atx-agent_0.0.3_linux_armv7.tar.gz',
        'arm64-v8a': 'atx-agent_0.0.3_linux_armv7.tar.gz',
        'armeabi': 'atx-agent_0.0.3_linux_armv6.tar.gz',
    }
    abis = adb('shell', 'getprop', 'ro.product.cpu.abilist').strip()
    name = None
    for abi in abis.split(','):
        name = files.get(abi)
        if name:
            break
    if not name:
        raise Exception("arch(%s) need to be supported yet, please report an issue in github" % abis)
    url = 'https://github.com/openatx/atx-agent/releases/download/%s/%s' % (__atx_agent_version, name)
    path = cache_download(url)
    # print(path)
    tar = tarfile.open(path, 'r:gz')
    bin_path = os.path.join(os.path.dirname(path), 'atx-agent')
    tar.extract('atx-agent', os.path.dirname(bin_path))
    adb('push', bin_path, '/data/local/tmp/atx-agent')
    adb('shell', 'chmod', '0755', '/data/local/tmp/atx-agent')

def check():
    log.info("launch atx-agent daemon")
    output = adb('shell', '/data/local/tmp/atx-agent', '-d')
    adb('forward', 'tcp:7912', 'tcp:7912')
    time.sleep(2)
    r = requests.get('http://localhost:7912/version', timeout=3)
    log.info("atx-agent version: %s", r.text)
    print('-'*20)
    print(output.strip())
    print('-'*20)

def main():
    abi = adb('shell', 'getprop', 'ro.product.cpu.abi').strip()
    sdk = adb('shell', 'getprop', 'ro.build.version.sdk').strip()
    pre = adb('shell', 'getprop', 'ro.build.version.preview_sdk').strip()
    log.info("device-info abi(%s), sdk(%s), pre(%s)", abi, sdk, pre)
    install_minicap(abi, sdk, pre)
    install_uiautomator_apk(sdk)
    install_atx_agent()
    log.info("checking")
    check()
    log.info("install success")


if __name__ == '__main__':
    main()