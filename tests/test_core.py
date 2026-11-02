# coding: utf-8
#

import hashlib
import json
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, mock_open, patch

import pytest

from uiautomator2.core import DEFAULT_SERVER_PORT, BasicUiautomatorServer, _http_request
from uiautomator2.exceptions import HTTPError, HTTPTimeoutError


@pytest.fixture
def mock_server():
    """Create a mock BasicUiautomatorServer instance with a mock device"""
    mock_dev = Mock()
    with patch.object(BasicUiautomatorServer, '__init__', return_value=None):
        server = BasicUiautomatorServer(None, DEFAULT_SERVER_PORT)
        server._dev = mock_dev
        server._device_server_port = DEFAULT_SERVER_PORT
        yield server, mock_dev


class TestCheckDeviceFileHash:
    """Test the _check_device_file_hash method with toybox fallback"""
    
    def test_toybox_md5sum_success(self, mock_server):
        """Test when toybox md5sum command works correctly"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        local_md5 = hashlib.md5(test_content).hexdigest()
        
        # Mock the shell command to return toybox md5sum output
        # Format: "md5hash  filename"
        mock_dev.shell.return_value = f"{local_md5}  /data/local/tmp/u2.jar"
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is True (hash matches)
        assert result is True
        # Verify toybox md5sum was called
        mock_dev.shell.assert_called_once_with(["toybox", "md5sum", "/data/local/tmp/u2.jar"])
    
    def test_toybox_not_found_fallback_to_md5(self, mock_server):
        """Test fallback to md5 command when toybox is not found"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        local_md5 = hashlib.md5(test_content).hexdigest()
        
        # Mock the shell command to return different outputs
        # First call: toybox not found
        # Second call: md5 command output (format: "MD5 (filename) = md5hash")
        mock_dev.shell.side_effect = [
            "toybox: not found",
            f"MD5 (/data/local/tmp/u2.jar) = {local_md5}"
        ]
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is True (hash matches)
        assert result is True
        # Verify both commands were called
        assert mock_dev.shell.call_count == 2
        assert mock_dev.shell.call_args_list[0][0][0] == ["toybox", "md5sum", "/data/local/tmp/u2.jar"]
        assert mock_dev.shell.call_args_list[1][0][0] == ["md5", "/data/local/tmp/u2.jar"]
    
    def test_hash_mismatch(self, mock_server):
        """Test when the hash doesn't match"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        different_md5 = hashlib.md5(b"different content").hexdigest()
        
        # Mock the shell command to return a different hash
        mock_dev.shell.return_value = f"{different_md5}  /data/local/tmp/u2.jar"
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is False (hash doesn't match)
        assert result is False
    
    def test_md5_command_also_fails(self, mock_server):
        """Test when both toybox and md5 commands fail to find the file"""
        server, mock_dev = mock_server
        
        # Create a temporary file with known content
        test_content = b"test content for md5"
        
        # Mock the shell command to return errors for both commands
        mock_dev.shell.side_effect = [
            "toybox: not found",
            "md5: /data/local/tmp/u2.jar: No such file or directory"
        ]
        
        # Mock the file read to return our test content
        with patch("builtins.open", mock_open(read_data=test_content)):
            result = server._check_device_file_hash("test.jar", "/data/local/tmp/u2.jar")
        
        # Verify the result is False (file not found on device)
        assert result is False


class FakeU2Handler(BaseHTTPRequestHandler):
    """Plays the uiautomator2 server, each request is handled by the next queued action"""

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        action = self.server.actions.pop(0)
        self.close_connection = True
        if action == "hang":
            self.server.released.wait(10)
        elif action == "reset":
            # SO_LINGER 0 makes close() send RST instead of FIN
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.connection.close()
        elif action == "short":
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b'{"jsonrpc": "2.0"')
        elif action != "close":
            body = json.dumps(action).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    do_GET = do_POST

    def log_message(self, format, *args):
        pass


@pytest.fixture
def fake_u2_server():
    """Local HTTP server standing in for the uiautomator2 server on the device"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeU2Handler)
    server.actions = []
    server.released = threading.Event()
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield server
    server.released.set()
    server.shutdown()
    server.server_close()


def connect_to(server):
    """Side effect for device.create_connection, returns a socket to the fake server"""
    def create_connection(network, port):
        sock = socket.create_connection(server.server_address)
        # adbutils returns the socket with its own long timeout (600s) set,
        # a shorter one here keeps a failing run from hanging
        sock.settimeout(5)
        return sock
    return create_connection


class TestHTTPRequest:
    """Test _http_request timeout and error mapping"""

    def test_timeout_is_applied(self, fake_u2_server):
        """Test the timeout argument overrides the timeout set on the adb socket"""
        fake_u2_server.actions.append("hang")
        mock_dev = Mock()
        mock_dev.create_connection.side_effect = connect_to(fake_u2_server)

        start = time.monotonic()
        with pytest.raises(HTTPTimeoutError):
            _http_request(mock_dev, DEFAULT_SERVER_PORT, "GET", "/ping", timeout=0.5)
        assert time.monotonic() - start < 3

    @pytest.mark.parametrize("action", ["close", "reset", "short"])
    def test_dropped_connection(self, fake_u2_server, action):
        """Test a connection dropped by the server raises HTTPError"""
        fake_u2_server.actions.append(action)
        mock_dev = Mock()
        mock_dev.create_connection.side_effect = connect_to(fake_u2_server)

        with pytest.raises(HTTPError):
            _http_request(mock_dev, DEFAULT_SERVER_PORT, "POST", "/jsonrpc/0", {"method": "ping"}, timeout=1)

    def test_jsonrpc_call_retries_after_dropped_connection(self, mock_server, fake_u2_server):
        """Test jsonrpc_call restarts the server and retries when the connection is dropped"""
        server, mock_dev = mock_server
        server._debug = False
        mock_dev.create_connection.side_effect = connect_to(fake_u2_server)
        fake_u2_server.actions.extend(["close", {"jsonrpc": "2.0", "id": 1, "result": "pong"}])

        with patch.object(server, "stop_uiautomator") as stop, patch.object(server, "start_uiautomator") as start:
            assert server.jsonrpc_call("ping") == "pong"
        stop.assert_called_once_with()
        start.assert_called_once_with()
