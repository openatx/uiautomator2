# coding: utf-8
#

import re
import socket
import subprocess
from collections import defaultdict


def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    try:
        return s.getsockname()[1]
    finally:
        s.close()


class Adb(object):
    def __init__(self, serial=None):
        self._serial = serial
    
    def execute(self, *args, **kwargs):
        cmds = ['adb', '-s', self._serial] if self._serial else ['adb']
        cmds.extend(args)
        cmdline = subprocess.list2cmdline(map(str, cmds))
        try:
            return subprocess.check_output(cmdline, stderr=subprocess.STDOUT, shell=True).decode('utf-8')
        except subprocess.CalledProcessError as e:
            if kwargs.get('raise_error', True):
                raise e
            return ''
    
    @property
    def serial(self):
        if self._serial:
            return self._serial
        self._serial = self.getprop('ro.serialno')
        return self._serial

    def forward(self, local, remote, rebind=True):
        if isinstance(local, int):
            local = 'tcp:%d' % local
        if isinstance(remote, int):
            remote = 'tcp:%d' % remote
        if rebind:
            return self.execute('forward', local, remote)
        else:
            return self.execute('forward', '--no-rebind', local, remote)
    
    def forward_list(self):
        """
        Only return tcp:<int> format forwards
        Returns:
            {
                "{RemotePort}": "{LocalPort}"
            }
        """
        output = self.execute('forward', '--list')
        ret = {}
        for groups in re.findall('([^\s]+)\s+tcp:(\d+)\s+tcp:(\d+)', output):
            if len(groups) != 3:
                continue
            serial, lport, rport = groups
            if serial != self.serial:
                continue
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
        args = ['shell'] + list(args)
        return self.execute(*args, **kwargs)

    def getprop(self, prop):
        return self.execute('shell', 'getprop', prop).strip()

    def push(self, src, dst, mode=0o644):
        self.execute('push', src, dst)
        if mode != 0o644:
            self.shell('chmod', oct(mode)[-3:], dst)
    
    def install(self, apk_path):
        sdk = self.getprop('ro.build.version.sdk')
        if int(sdk) <= 23:
            self.execute('install', '-d', '-r', apk_path)
        else:
            self.execute('install', '-d', '-r', '-g', apk_path)
    
    def uninstall(self, pkg_name):
        return self.execute('uninstall', pkg_name, raise_error=False)

    def package_info(self, pkg_name):
        output = self.shell('dumpsys', 'package', pkg_name)
        m = re.compile(r'versionName=(?P<name>[\d.]+)').search(output)
        version_name = m.group('name') if m else None
        m = re.search(r'PackageSignatures\{(.*?)\}', output)
        signature = m.group(1) if m else None
        return dict(version_name=version_name, signature=signature)