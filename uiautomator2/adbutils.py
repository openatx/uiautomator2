# coding: utf-8
#
# Refs: https://github.com/openatx/uiautomator2/blob/d08e2e8468/uiautomator2/adbutils.py

from __future__ import print_function

import os
import re
import socket
import struct
import subprocess
from collections import namedtuple

import six
import whichcraft

_OKAY = "OKAY"
_FAIL = "FAIL"
_DENT = "DENT"  # Directory Entity
_DONE = "DONE"

DeviceItem = namedtuple("Device", ["serial", "status"])
ForwardItem = namedtuple("ForwardItem", ["serial", "local", "remote"])


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    try:
        return s.getsockname()[1]
    finally:
        s.close()


def adb_path():
    path = whichcraft.which("adb")
    if path is None:
        raise EnvironmentError(
            "Can't find the adb, please install adb on your PC")
    return path


class AdbError(Exception):
    """ adb error """


class _AdbStreamConnection(object):
    def __init__(self, host=None, port=None):
        # assert isinstance(host, six.string_types)
        # assert isinstance(port, int)
        self.__host = host
        self.__port = port
        self.__conn = None

    def connect(self):
        adb_host = self.__host or os.environ.get("ANDROID_ADB_SERVER_HOST",
                                                 "127.0.0.1")
        adb_port = self.__port or int(
            os.environ.get("ANDROID_ADB_SERVER_PORT", 5037))
        self.__conn
        s = self.__conn = socket.socket()
        s.connect((adb_host, adb_port))
        return self

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, traceback):
        self.conn.close()

    @property
    def conn(self):
        return self.__conn

    def send(self, cmd):
        assert isinstance(cmd, six.string_types)
        self.conn.send("{:04x}{}".format(len(cmd), cmd).encode("utf-8"))

    def read(self, n):
        assert isinstance(n, int)
        return self.conn.recv(n).decode()

    def read_string(self):
        size = int(self.read(4), 16)
        return self.read(size)

    def read_until_close(self):
        content = ""
        while True:
            chunk = self.read(4096)
            if not chunk:
                break
            content += chunk
        return content

    def check_okay(self):
        data = self.read(4)
        if data == _FAIL:
            raise AdbError(self.read_string())
        elif data == _OKAY:
            return
        raise AdbError("Unknown data: %s" % data)


class AdbClient(object):
    def connect(self):
        return _AdbStreamConnection()

    def server_version(self):
        """ 40 will match 1.0.40
        Returns:
            int
        """
        with self.connect() as c:
            c.send("host:version")
            c.check_okay()
            return int(c.read_string(), 16)

    def shell(self, serial, command):
        """Run shell in android and return output
        Args:
            serial (str)
            command: list, tuple or str
        
        Returns:
            str
        """
        assert isinstance(serial, six.string_types)
        if isinstance(command, (list, tuple)):
            command = subprocess.list2cmdline(command)
        assert isinstance(command, six.string_types)
        with self.connect() as c:
            c.send("host:transport:" + serial)
            c.check_okay()
            c.send("shell:" + command)
            return c.read_until_close()

    def forward_list(self):
        with self.connect() as c:
            c.send("host:list-forward")
            c.check_okay()
            content = c.read_string()
            for line in content.splitlines():
                parts = line.split()
                if len(parts) != 3:
                    continue
                yield ForwardItem(*parts)

    def forward(self, serial, local, remote, norebind=False):
        """
        Args:
            serial (str): device serial
            local, remote (str): tcp:<port> or localabstract:<name>
            norebind (bool): fail if already forwarded when set to true
        
        Raises:
            AdbError
        """
        with self.connect() as c:
            cmds = ["host-serial", serial, "forward"]
            if norebind:
                cmds.append("norebind")
            cmds.append(local + ";" + remote)
            c.send(":".join(cmds))
            c.check_okay()

    def listdir(self, serial, path):
        assert isinstance(serial, six.string_types)
        assert isinstance(path, six.string_types)

        with self.connect() as c:
            c.send(":".join(["host", "transport", serial]))
            c.check_okay()
            c.send("sync:")
            c.check_okay()
            # {COMMAND}{LittleEndianPathLength}{Path}
            c.conn.send(b"LIST" + struct.pack("<I", len(path)) +
                        path.encode("utf-8"))

            while 1:
                response = c.read(4)
                if response == _DONE:
                    break
                print("N: %o" % struct.unpack("<I", c.conn.recv(4)))
                print("Size: ", struct.unpack("<I", c.conn.recv(4)))
                print("MTime: ", struct.unpack("<I", c.conn.recv(4)))
                name_size = struct.unpack("<I", c.conn.recv(4))[0]
                print("Name:", c.read(name_size))
            # print(c.read_string())

    def iter_device(self):
        """
        Returns:
            list of DeviceItem
        """
        with self.connect() as c:
            c.send("host:devices")
            c.check_okay()
            output = c.read_string()
            for line in output.splitlines():
                parts = line.strip().split("\t")
                if len(parts) != 2:
                    continue
                if parts[1] == 'device':
                    yield AdbDevice(self, parts[0])

    def devices(self):
        return list(self.iter_device())

    def must_one_device(self):
        ds = self.devices()
        if len(ds) == 0:
            raise RuntimeError("Can't find any android device/emulator")
        if len(ds) > 1:
            raise RuntimeError(
                "more than one device/emulator, please specify the serial number"
            )
        return ds[0]


class AdbDevice(object):
    def __init__(self, client, serial):
        self._client = client
        self._serial = serial

    @property
    def serial(self):
        return self._serial

    def adb_output(self, *args, **kwargs):
        """Run adb command and get its content

        Returns:
            string of output

        Raises:
            EnvironmentError
        """

        cmds = [adb_path(), '-s', self._serial
                ] if self._serial else [adb_path()]
        cmds.extend(args)
        cmdline = subprocess.list2cmdline(map(str, cmds))
        try:
            return subprocess.check_output(
                cmdline, stderr=subprocess.STDOUT, shell=True).decode('utf-8')
        except subprocess.CalledProcessError as e:
            if kwargs.get('raise_error', True):
                raise EnvironmentError(
                    "subprocess", cmdline,
                    e.output.decode('utf-8', errors='ignore'))

    def shell_output(self, *args):
        return self._client.shell(self._serial, subprocess.list2cmdline(args))

    def forward_port(self, remote_port):
        assert isinstance(remote_port, int)
        for f in self._client.forward_list():
            if f.serial == self._serial and f.remote == 'tcp:' + str(
                    remote_port) and f.local.startswith("tcp:"):
                return int(f.local[len("tcp:"):])
        local_port = get_free_port()
        self._client.forward(self._serial, "tcp:" + str(local_port),
                             "tcp:" + str(remote_port))
        return local_port

    def push(self, local, remote):
        assert isinstance(local, six.string_types)
        assert isinstance(remote, six.string_types)
        self.adb_output("push", local, remote)

    def install(self, apk_path):
        """
        sdk = self.getprop('ro.build.version.sdk')
        sdk > 23 support -g
        """
        assert isinstance(apk_path, six.string_types)
        self.adb_output("install", "-r", apk_path)

    def uninstall(self, pkg_name):
        assert isinstance(pkg_name, six.string_types)
        self.adb_output("uninstall", pkg_name)

    def getprop(self, prop):
        assert isinstance(prop, six.string_types)
        return self.shell_output('getprop', prop).strip()

    def package_info(self, pkg_name):
        assert isinstance(pkg_name, six.string_types)
        output = self.shell_output('dumpsys', 'package', pkg_name)
        m = re.compile(r'versionName=(?P<name>[\d.]+)').search(output)
        version_name = m.group('name') if m else None
        m = re.search(r'PackageSignatures\{(.*?)\}', output)
        signature = m.group(1) if m else None
        if version_name is None and signature is None:
            return None
        return dict(version_name=version_name, signature=signature)


if __name__ == "__main__":
    adb = AdbClient()
    print("server version:", adb.server_version())
    print("devices:", adb.devices())
    d = adb.devices()[0]

    print(d.serial)
    adb.listdir("bf755cab", "/data/local/tmp/")
