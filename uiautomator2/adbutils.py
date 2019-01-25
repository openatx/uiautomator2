# coding: utf-8
#

from __future__ import print_function

import re
import socket
import whichcraft
import subprocess
from adb.client import Client as AdbClient
from adb import InstallError


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    try:
        return s.getsockname()[1]
    finally:
        s.close()


def devices():
    client = AdbClient(
        host='127.0.0.1', port=5037)  # TODO(ssx): should get HOST from env
    return client.devices()


class Adb(object):
    def __init__(self, serial=None, host="127.0.0.1", port=5037):
        self._serial = serial
        self._client = AdbClient(host=host, port=port)

        try:
            self._client.version()
        except RuntimeError:
            # Can't connect to the adb server, try to start the adb server by command line.
            self._start_adb_server()

        if self._serial:
            self._device = self._client.device(serial)
        else:
            # The serial can be None only when there is only one device/emulator.
            devices = self._client.devices()
            if len(devices) == 0:
                raise RuntimeError("Can't find any android device/emulator")
            elif len(devices) > 1:
                raise RuntimeError(
                    "more than one device/emulator, please specify the serial number"
                )
            else:
                device = devices[0]
                self._serial = device.get_serial_no()
                self._device = device

    @staticmethod
    def list_devices(host="127.0.0.1", port=5037):
        client = AdbClient(host=host, port=port)

        try:
            client.version()
        except RuntimeError:
            # Can't connect to the adb server, try to start the adb server by command line.
            Adb._start_adb_server()

        return client.devices()

    @staticmethod
    def _start_adb_server():
        adb_path = whichcraft.which("adb")
        if adb_path is None:
            raise EnvironmentError(
                "Can't find the adb, please install adb on your PC")

        cmd = [adb_path, "start-server"]
        cmdline = subprocess.list2cmdline(cmd)
        try:
            return subprocess.check_output(
                cmdline, stderr=subprocess.STDOUT, shell=True).decode('utf-8')
        except subprocess.CalledProcessError as e:
            raise EnvironmentError("subprocess", cmdline,
                                   e.output.decode('utf-8', errors='ignore'))

    # def devices(self, states=['device', 'offline']):
    #     """
    #     Returns:
    #         [($serial1, "device"), ($serial2, "offline")]
    #     """
    #     # TODO: not really checking anything
    #     return [(d, "device") for d in self.list_devices()]
    #     output = subprocess.check_output([self.adb_path(), 'devices'])
    #     pattern = re.compile(r'(?P<serial>[^\s]+)\t(?P<status>device|offline)')
    #     matches = pattern.findall(output.decode())
    #     return [(m[0], m[1]) for m in matches]

    @property
    def serial(self):
        return self._serial

    def forward(self, local, remote, rebind=True):
        if isinstance(local, int):
            local = 'tcp:%d' % local
        if isinstance(remote, int):
            remote = 'tcp:%d' % remote

        return self._device.forward(local, remote, norebind=not rebind)

    def forward_list(self):
        """
        Only return tcp:<int> format forwards
        Returns:
            {
                "{RemotePort}": "{LocalPort}"
            }
        """

        # TODO(ssx): There is a bug in pure-python-adb "forward_list"
        # waiting for the lib author to fixit.
        # original code --.
        # forward_list = self._device.list_forward()

        cmd = "host-serial:{serial}:list-forward".format(serial=self.serial)
        result = self._device._execute_cmd(cmd)

        forward_list = {}

        for line in result.split('\n'):
            if not line:
                continue
            serial, local, remote = line.split()
            if serial != self._device.serial:
                continue
            forward_list[local] = remote

        ret = {}

        for local, remote in forward_list.items():
            ltype, lport = local.split(":")
            rtype, rport = remote.split(":")

            if ltype == "tcp" and rtype == "tcp":
                ret[int(rport)] = int(lport)

        return ret

    def forward_port(self, remote_port):
        forwards = self.forward_list()
        lport = forwards.get(remote_port)
        if lport:
            return lport
        free_port = find_free_port()
        self.forward(free_port, remote_port)
        return free_port

    def shell(self, *args, **kwargs):
        return self._device.shell(" ".join(args))

    def getprop(self, prop):
        return self.shell('getprop', prop).strip()

    def push(self, src, dst, mode=0o644):
        self._device.push(src, dst, mode=mode)

    def install(self, apk_path):
        sdk = self.getprop('ro.build.version.sdk')
        if int(sdk) <= 23:
            self._device.install(apk_path, reinstall=True, downgrade=True)
            return
        try:
            # some device is missing -g
            self._device.install(
                apk_path,
                reinstall=True,
                downgrade=True,
                grand_all_permissions=True)
        except InstallError:
            self._device.install(apk_path, reinstall=True, downgrade=True)

    def uninstall(self, pkg_name):
        return self._device.uninstall(pkg_name)

    def package_info(self, pkg_name):
        output = self.shell('dumpsys', 'package', pkg_name)
        m = re.compile(r'versionName=(?P<name>[\d.]+)').search(output)
        version_name = m.group('name') if m else None
        m = re.search(r'PackageSignatures\{(.*?)\}', output)
        signature = m.group(1) if m else None
        if version_name is None and signature is None:
            return None
        return dict(version_name=version_name, signature=signature)
