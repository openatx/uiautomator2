# coding: utf-8
#

import datetime
import hashlib
import logging
import os
from pathlib import Path
import shutil
import tarfile

import adbutils
import progress.bar
import requests
from retry import retry

from uiautomator2.utils import natualsize
from uiautomator2.version import __apk_version__, __atx_agent_version__, __jar_version__, __version__

appdir = os.path.join(os.path.expanduser("~"), '.uiautomator2')

GITHUB_BASEURL = "https://github.com/openatx"


logger = logging.getLogger(__name__)
assets_dir = Path(__file__).absolute().parent.joinpath("assets")

class DownloadBar(progress.bar.PixelBar):
    message = "Downloading"
    suffix = '%(current_size)s/%(total_size)s'
    width = 10

    @property
    def total_size(self):
        return natualsize(self.max)

    @property
    def current_size(self):
        return natualsize(self.index)


def gen_cachepath(url: str) -> str:
    filename = os.path.basename(url)
    storepath = os.path.join(
        appdir, "cache",
        filename.replace(" ", "_") + "-" +
        hashlib.sha224(url.encode()).hexdigest()[:10], filename)
    return storepath

def cache_download(url, filename=None, timeout=None, storepath=None, logger=logger):
    """ return downloaded filepath """
    # check cache
    if not filename:
        filename = os.path.basename(url)
    if not storepath:
        storepath = gen_cachepath(url)
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
    with open(storepath + '.part', 'wb') as f:
        chunk_length = 16 * 1024
        while 1:
            buf = r.raw.read(chunk_length)
            if not buf:
                break
            f.write(buf)
            bar.next(len(buf))
        bar.finish()

    assert file_size == os.path.getsize(storepath +
                                        ".part")  # may raise FileNotFoundError
    shutil.move(storepath + '.part', storepath)
    return storepath

def mirror_download(url: str, filename=None):
    """
    Download from mirror, then fallback to origin url
    """
    storepath = gen_cachepath(url)
    if not filename:
        filename = os.path.basename(url)
    github_host = "https://github.com"
    if url.startswith(github_host):
        mirror_url = "https://tool.appetizer.io" + url[len(
            github_host):]  # mirror of github
        try:
            return cache_download(mirror_url,
                                  filename,
                                  timeout=60,
                                  storepath=storepath,
                                  logger=logger)
        except (requests.RequestException, FileNotFoundError,
                AssertionError) as e:
            logger.debug("download error from mirror(%s), use origin source", e)

    return cache_download(url, filename, storepath=storepath, logger=logger)


def app_uiautomator_apk_urls():
    ret = []
    for name in ["app-uiautomator.apk", "app-uiautomator-test.apk"]:
        ret.append((name, "".join([
            GITHUB_BASEURL, "/android-uiautomator-server/releases/download/",
            __apk_version__, "/", name
        ])))
    return ret


def parse_apk(path: str):
    """
    Parse APK
    
    Returns:
        dict contains "package" and "main_activity"
    """
    import apkutils2
    apk = apkutils2.APK(path)
    package_name = apk.manifest.package_name
    main_activity = apk.manifest.main_activity
    return {
        "package": package_name,
        "main_activity": main_activity,
    }

class Initer():
    def __init__(self, device: adbutils.AdbDevice, loglevel=logging.DEBUG):
        d = self._device = device

        self.sdk = d.getprop('ro.build.version.sdk')
        self.abi = d.getprop('ro.product.cpu.abi')
        self.pre = d.getprop('ro.build.version.preview_sdk')
        self.arch = d.getprop('ro.arch')
        self.abis = (d.getprop('ro.product.cpu.abilist').strip()
                     or self.abi).split(",")
        
        self.__atx_listen_addr = "127.0.0.1:7912"
        logger.info("uiautomator2 version: %s", __version__)

    def set_atx_agent_addr(self, addr: str):
        assert ":" in addr
        self.__atx_listen_addr = addr

    @property
    def atx_agent_path(self):
        return "/data/local/tmp/atx-agent"

    def shell(self, *args, timeout=60):
        logger.debug("Shell: %s", args)
        return self._device.shell(args, timeout=60)

    @property
    def jar_urls(self):
        """
        Returns:
            iter([name, url], [name, url])
        """
        for name in ['bundle.jar', 'uiautomator-stub.jar']:
            yield (name, "".join([
                GITHUB_BASEURL,
                "/android-uiautomator-jsonrpcserver/releases/download/",
                __jar_version__, "/", name
            ]))

    @property
    def atx_agent_url(self):
        files = {
            'armeabi-v7a': 'atx-agent_{v}_linux_armv7.tar.gz',
            'arm64-v8a': 'atx-agent_{v}_linux_arm64.tar.gz',
            'armeabi': 'atx-agent_{v}_linux_armv6.tar.gz',
            'x86': 'atx-agent_{v}_linux_386.tar.gz',
            'x86_64': 'atx-agent_{v}_linux_386.tar.gz',
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
        """
        binary from https://github.com/openatx/stf-binaries
        only got abi: armeabi-v7a and arm64-v8a
        """
        base_url = GITHUB_BASEURL + \
            "/stf-binaries/raw/0.3.0/node_modules/@devicefarmer/minicap-prebuilt/prebuilt/"
        sdk = self.sdk
        yield base_url + self.abi + "/lib/android-" + sdk + "/minicap.so"
        yield base_url + self.abi + "/bin/minicap"

    @property
    def minitouch_url(self):
        return ''.join([
            GITHUB_BASEURL + "/stf-binaries",
            "/raw/0.3.0/node_modules/@devicefarmer/minitouch-prebuilt/prebuilt/",
            self.abi + "/bin/minitouch"
        ])

    @retry(tries=2, logger=logger)
    def push_url(self, url, dest=None, mode=0o755, tgz=False, extract_name=None):  # yapf: disable
        path = mirror_download(url, filename=os.path.basename(url))
        if tgz:
            tar = tarfile.open(path, 'r:gz')
            path = os.path.join(os.path.dirname(path), extract_name)
            tar.extract(extract_name,
                        os.path.dirname(path))  # zlib.error may raise

        if not dest:
            dest = "/data/local/tmp/" + os.path.basename(path)

        logger.debug("Push to %s:0%o", dest, mode)
        self._device.sync.push(path, dest, mode=mode)
        return dest

    def is_apk_outdated(self):
        """
        If apk signature mismatch, the uiautomator test will fail to start
        command: am instrument -w -r -e debug false \
                -e class com.github.uiautomator.stub.Stub \
                com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner
        java.lang.SecurityException: Permission Denial: \
            starting instrumentation ComponentInfo{com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner} \
            from pid=7877, uid=7877 not allowed \
            because package com.github.uiautomator.test does not have a signature matching the target com.github.uiautomator
        """
        apk_debug = self._device.package_info("com.github.uiautomator")
        apk_debug_test = self._device.package_info(
            "com.github.uiautomator.test")
        logger.debug("apk-debug package-info: %s", apk_debug)
        logger.debug("apk-debug-test package-info: %s", apk_debug_test)
        if not apk_debug or not apk_debug_test:
            return True
        if apk_debug['version_name'] != __apk_version__:
            logger.info(
                "package com.github.uiautomator version %s, latest %s",
                apk_debug['version_name'], __apk_version__)
            return True

        if apk_debug['signature'] != apk_debug_test['signature']:
            # On vivo-Y67 signature might not same, but signature matched.
            # So here need to check first_install_time again
            max_delta = datetime.timedelta(minutes=3)
            if abs(apk_debug['first_install_time'] -
                   apk_debug_test['first_install_time']) > max_delta:
                logger.debug(
                    "package com.github.uiautomator does not have a signature matching the target com.github.uiautomator"
                )
                return True
        return False

    def is_atx_agent_outdated(self):
        """
        Returns:
            bool
        """
        agent_version = self._device.shell([self.atx_agent_path, "version"]).strip()
        if agent_version == "dev":
            logger.info("skip version check for atx-agent dev")
            return False

        # semver major.minor.patch
        try:
            real_ver = list(map(int, agent_version.split(".")))
            want_ver = list(map(int, __atx_agent_version__.split(".")))
        except ValueError:
            return True

        logger.debug("Real version: %s, Expect version: %s", real_ver,
                          want_ver)

        if real_ver[:2] != want_ver[:2]:
            return True

        return real_ver[2] < want_ver[2]

    def check_install(self):
        """
        Only check atx-agent and test apks (Do not check minicap and minitouch)

        Returns:
            True if everything is fine, else False
        """
        d = self._device
        if d.sync.stat(self.atx_agent_path).size == 0:
            return False

        if self.is_atx_agent_outdated():
            return False

        if self.is_apk_outdated():
            return False

        return True

    def _install_uiautomator_apks(self):
        """ use uiautomator 2.0 to run uiautomator test
        通常在连接USB数据线的情况下调用
        """
        self.shell("pm", "uninstall", "com.github.uiautomator")
        self.shell("pm", "uninstall", "com.github.uiautomator.test")
        for filename, url in app_uiautomator_apk_urls():
            path = self.push_url(url, mode=0o644)
            self.shell("pm", "install", "-r", "-t", path)
            logger.info("- %s installed", filename)

    def _install_jars(self):
        """ use uiautomator 1.0 to run uiautomator test """
        for (name, url) in self.jar_urls:
            self.push_url(url, "/data/local/tmp/" + name, mode=0o644)

    def _install_atx_agent(self):
        logger.info("Install atx-agent %s", __atx_agent_version__)
        if 'armeabi' in self.abis:
            local_atx_agent_path = assets_dir.joinpath("atx-agent")
            if local_atx_agent_path.exists():
                logger.info("Use local atx-agent[armeabi]: %s", local_atx_agent_path)
                dest = '/data/local/tmp/atx-agent'
                self._device.sync.push(local_atx_agent_path, dest, mode=0o755)
                return
        self.push_url(self.atx_agent_url, tgz=True, extract_name="atx-agent")

    def setup_atx_agent(self):
        # stop atx-agent first
        self.shell(self.atx_agent_path, "server", "--stop")
        if self.is_atx_agent_outdated():
            self._install_atx_agent()
        
        self.shell(self.atx_agent_path, 'server', '--nouia', '-d', "--addr", self.__atx_listen_addr)
        logger.info("Check atx-agent version")
        self.check_atx_agent_version()

    @retry(
        (requests.ConnectionError, requests.ReadTimeout, requests.HTTPError),
        delay=.5,
        tries=10)
    def check_atx_agent_version(self):
        port = self._device.forward_port(7912)
        logger.debug("Forward: local:tcp:%d -> remote:tcp:%d", port, 7912)
        version = requests.get("http://%s:%d/version" %
                               (self._device._client.host, port)).text.strip()
        logger.debug("atx-agent version %s", version)

        wlan_ip = requests.get("http://%s:%d/wlan/ip" %
                               (self._device._client.host, port)).text.strip()
        logger.debug("device wlan ip: %s", wlan_ip)
        return version

    def install(self):
        """
        TODO: push minicap and minitouch from tgz file
        """
        logger.info("Install minicap, minitouch")
        self.push_url(self.minitouch_url)
        if self.abi == "x86":
            logger.info(
                "abi:x86 not supported well, skip install minicap")
        elif int(self.sdk) > 30:
            logger.info("Android R (sdk:30) has no minicap resource")
        else:
            for url in self.minicap_urls:
                self.push_url(url)

        # self._install_jars() # disable jars
        if self.is_apk_outdated():
            logger.info(
                "Install com.github.uiautomator, com.github.uiautomator.test %s",
                __apk_version__)
            self._install_uiautomator_apks()
        else:
            logger.info("Already installed com.github.uiautomator apks")

        self.setup_atx_agent()
        print("Successfully init %s" % self._device)

    def uninstall(self):
        self._device.shell([self.atx_agent_path, "server", "--stop"])
        self._device.shell(["rm", self.atx_agent_path])
        logger.info("atx-agent stopped and removed")
        self._device.shell(["rm", "/data/local/tmp/minicap"])
        self._device.shell(["rm", "/data/local/tmp/minicap.so"])
        self._device.shell(["rm", "/data/local/tmp/minitouch"])
        logger.info("minicap, minitouch removed")
        self._device.shell(["pm", "uninstall", "com.github.uiautomator"])
        self._device.shell(["pm", "uninstall", "com.github.uiautomator.test"])
        logger.info("com.github.uiautomator uninstalled, all done !!!")


if __name__ == "__main__":
    import adbutils

    serial = None
    device = adbutils.adb.device(serial)
    init = Initer(device, loglevel=logging.DEBUG)
    print(init.check_install())
