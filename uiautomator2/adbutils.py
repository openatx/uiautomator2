import struct
import time
import os
import re
import shlex
import socket
import socket as Socket
import six

if six.PY2:
    from pipes import quote
else: # for py3
    from shlex import quote

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 0))
    try:
        return s.getsockname()[1]
    finally:
        s.close()


class Protocol:
    OKAY = 'OKAY'
    FAIL = 'FAIL'
    STAT = 'STAT'
    LIST = 'LIST'
    DENT = 'DENT'
    RECV = 'RECV'
    DATA = 'DATA'
    DONE = 'DONE'
    SEND = 'SEND'
    QUIT = 'QUIT'

    @staticmethod
    def decode_length(length):
        return int(length, 16)

    @staticmethod
    def encode_length(length):
        return "{0:04X}".format(length)

    @staticmethod
    def encode_data(data):
        b_data = data.encode('utf-8')
        b_length = Protocol.encode_length(len(b_data)).encode('utf-8')
        return b"".join([b_length, b_data])


class Connection:
    def __init__(self, host='localhost', port=5037, socket_timeout=30):
        self.host = host
        self.port = port
        self.socket_timeout = socket_timeout
        self.socket = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def connect(self):

        self.socket = Socket.socket(Socket.AF_INET, Socket.SOCK_STREAM)

        l_onoff = 1
        l_linger = 0

        self.socket.setsockopt(Socket.SOL_SOCKET, Socket.SO_LINGER, struct.pack('ii', l_onoff, l_linger))
        self.socket.settimeout(self.socket_timeout)

        try:
            self.socket.connect((self.host, self.port))
        except Socket.error as e:
            raise RuntimeError("ERROR: connecting to {}:{} {}.\nIs adb running on your computer?".format(
                self.host,
                self.port,
                e
            ))

        return self.socket

    def close(self):
        self.socket.close()

    def receive(self):
        nob = int(self.socket.recv(4).decode('utf-8'), 16)
        recv = bytearray(nob)
        view = memoryview(recv)
        self.socket.recv_into(view)

        return recv.decode('utf-8')

    def send(self, msg):
        msg = Protocol.encode_data(msg)
        self.socket.send(msg)
        return self._check_status()

    def _check_status(self):
        recv = self.socket.recv(4).decode('utf-8')
        if recv != Protocol.OKAY:
            error = self.socket.recv(1024).decode('utf-8')
            raise RuntimeError("ERROR: {} {}".format(repr(recv), error))

        return True

    def read(self):
        data = b''

        while True:
            recv = self.socket.recv(4096)
            if not recv:
                break
            data += recv

        return data

    def write(self, data):
        self.socket.send(data)


class Sync:
    DEFAULT_CHMOD = 0o644
    DATA_MAX_LENGTH = 65536

    S_IFREG = 0o100000  # regular file

    def __init__(self, connection):
        self.connection = connection

    def push(self, src, dest, mode=0o644):
        stream = open(src, 'rb')
        timestamp = int(time.time())

        # SEND
        mode |= self.S_IFREG
        args = "{dest},{mode}".format(
            dest=dest,
            mode=mode
        )
        self._send_str(Protocol.SEND, args)

        # DATA
        while True:
            chunk = stream.read(self.DATA_MAX_LENGTH)
            if not chunk:
                break

            self._send_length(Protocol.DATA, len(chunk))
            self.connection.write(chunk)

        # DONE
        self._send_length(Protocol.DONE, timestamp)
        self.connection._check_status()

    def _little_endian(self, n):
        return struct.pack('<I', n)

    def _send_length(self, cmd, length):
        le_len = self._little_endian(length)
        data = cmd.encode() + le_len

        self.connection.write(data)

    def _send_str(self, cmd, args):
        """
        Format:
            {Command}{args length(little endian)}{str}
        Length:
            {4}{4}{str length}
        """
        args = args.encode('utf-8')

        le_args_len = self._little_endian(len(args))
        data = cmd.encode() + le_args_len + args
        self.connection.write(data)


class Device:
    def __init__(self, client, serial, status):
        self.client = client
        self.serial = serial
        self.status = status

    def create_connection(self, set_transport=True):
        conn = self.client.create_connection()
        conn.connect()

        if set_transport:
            cmd = "host:transport:{}".format(self.serial)
            conn.send(cmd)

        return conn

    def sync(self):
        conn = self.create_connection()

        cmd = "sync:"
        conn.send(cmd)

        return conn

    def shell(self, *args):
        cmd = " ".join(args)
        conn = self.create_connection()

        with conn:
            cmd = "shell:{}".format(cmd)
            conn.send(cmd)

            result = conn.read()
            return result.decode('utf-8')

    def getprop(self, prop):
        return self.shell('getprop {}'.format(prop)).strip()

    def push(self, src, dest, mode=0o644):
        # Create a new connection for file transfer
        sync_conn = self.sync()
        sync = Sync(sync_conn)

        with sync_conn:
            sync.push(src, dest, mode)

    def forward_port(self, remote):
        local = find_free_port()
        conn = self.create_connection(set_transport=False)

        with conn:
            cmd = "host-serial:{serial}:forward:tcp:{local};tcp:{remote}".format(
                serial=self.serial,
                local=local,
                remote=remote)

            conn.send(cmd)

        return local

    def list_forward(self):
        conn = self.create_connection(set_transport=False)

        with conn:
            cmd = "host-serial:{serial}:list-forward".format(serial=self.serial)
            conn.send(cmd)
            result = conn.receive()

        forward_map = {}

        for line in result.split('\n'):
            if line:
                _, local, remote = line.split()
                forward_map[local] = remote

        return forward_map

    def install(self, path):
        tmp_path = "/data/local/tmp/{}".format(os.path.basename(path))
        self.push(path, tmp_path)

        try:
            sdk = self.getprop("ro.build.version.sdk")
            if int(sdk) <= 23:
                result = self.shell("pm", "install", "-d", "-r", quote(tmp_path))
            else:
                result = self.shell("pm", "install", "-d", "-r", "-g", quote(tmp_path))

            match = re.search("(Success|Failure|Error)\s?(.*)", result)

            if match and match.group(1) == "Success":
                return True
            else:
                raise RuntimeError("Can't install {} - {}".format(path, result))
        finally:
            self.shell("rm -f {}".format(tmp_path))

    def uninstall(self, pkg_name):
        result = self.shell('pm uninstall {}'.format(pkg_name))
        match = re.search('(Success|Failure.*|.*Unknown package:.*)', result)

        if match and match.group(1) == "Success":
            return True
        else:
            return False

    def package_info(self, pkg_name):
        output = self.shell('dumpsys package {}'.format(pkg_name))
        m = re.compile(r'versionName=(?P<name>[\d.]+)').search(output)
        version_name = m.group('name') if m else None
        m = re.search(r'PackageSignatures\{(.*?)\}', output)
        signature = m.group(1) if m else None
        return dict(version_name=version_name, signature=signature)


class Client:
    def __init__(self, host='localhost', port=5037, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout

    def create_connection(self):
        conn = Connection(self.host, self.port, self.timeout)
        conn.connect()
        return conn

    def devices(self):
        with self.create_connection() as conn:
            cmd = "host:devices"
            conn.send(cmd)
            result = conn.receive()

            devices = []

            pattern = re.compile(r'(?P<serial>[^\s]+)\t(?P<status>device|offline)')
            matches = pattern.findall(result)
            for m in matches:
                serial, status = m[0], m[1]
                devices.append(Device(self, serial, status))

            return devices

    def device(self, serial):
        devices = self.devices()

        if serial is None and devices:
            return devices[0]
        else:
            for device in devices:
                if device.serial == serial:
                    return device

        return None
