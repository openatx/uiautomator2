#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Thu Apr 25 2024 14:50:05 by codeskyblue
"""

import atexit
import datetime
import hashlib
import os
import threading
import time
import logging
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

import adbutils
import requests

from uiautomator2.exceptions import RPCInvalidError, RPCStackOverflowError, UiAutomationNotConnectedError, HTTPError, LaunchUiAutomationError, UiObjectNotFoundError, RPCUnknownError, APKSignatureError, AccessibilityServiceAlreadyRegisteredError
from uiautomator2.abstract import AbstractUiautomatorServer
from uiautomator2.utils import is_version_compatiable
from uiautomator2.version import __apk_version__


logger = logging.getLogger(__name__)

class MockAdbProcess:
    def __init__(self, conn: adbutils.AdbConnection) -> None:
        self._conn = conn
        self._event = threading.Event()
        self._output = bytearray()
        def wait_finished():
            try:
                while chunk := self._conn.conn.recv(1024):
                    logger.debug("MockAdbProcess: %s", chunk)
                    self._output.extend(chunk)
            except:
                pass
            self._event.set()
        
        t = threading.Thread(target=wait_finished)
        t.daemon = True
        t.name = "wait_adb_conn"
        t.start()
    
    @property
    def output(self) -> bytes:
        """ subprocess do not have this property """
        return self._output

    def wait(self) -> int:
        self._event.wait()
        return 0

    def pool(self) -> Optional[int]:
        if self._event.is_set():
            return 0
        return None

    def kill(self):
        self._conn.close()
        self.wait()


def launch_uiautomator(dev: adbutils.AdbDevice) -> MockAdbProcess:
    """Launch uiautomator2 server on device"""
    command = "CLASSPATH=/data/local/tmp/u2.jar app_process / com.wetest.uia2.Main"
    logger.debug("launch uiautomator with cmd: %s", command)
    conn = dev.shell(command, stream=True)
    process = MockAdbProcess(conn)
    return process


class HTTPResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
    
    def json(self):
        return json.loads(self.content)

    @property
    def text(self):
        return self.content.decode("utf-8", errors="ignore")


def _http_request(dev: adbutils.AdbDevice, method: str, path: str, data: Dict[str, Any] = None, timeout=10, print_request: bool = False) -> HTTPResponse:
    """Send http request to uiautomator2 server"""
    try:
        logger.debug("http request %s %s %s", method, path, data)
        lport = dev.forward_port(9008)
        logger.debug("forward tcp:%d -> tcp:9008", lport)
        # https://stackoverflow.com/questions/2386299/running-sites-on-localhost-is-extremely-slow
        # so here use 127.0.0.1 instead of localhost
        url = f"http://127.0.0.1:{lport}{path}"
        if print_request:
            start_time = datetime.datetime.now()
            current_time = start_time.strftime("%H:%M:%S.%f")[:-3]
            fields = [current_time, f"$ curl -X {method}", url]
            if data:
                fields.append(f"-d '{json.dumps(data)}'")
            print(f"# http timeout={timeout}")
            print(" ".join(fields))
        r = requests.request(method, url, json=data, timeout=timeout)
        r.raise_for_status()
        response = HTTPResponse(r.content)
        if print_request:
            end_time = datetime.datetime.now()
            current_time = end_time.strftime("%H:%M:%S.%f")[:-3]
            print(f"{current_time} Response >>>")
            print(response.text.rstrip())
            print(f"<<< END timed_used = %.3f\n" % (end_time - start_time).total_seconds())
        return response
    except requests.RequestException as e:
        raise HTTPError(f"HTTP request failed: {e}") from e


def _jsonrpc_call(dev: adbutils.AdbDevice, method: str, params: Any, timeout: float, print_request: bool) -> Any:
    """Send jsonrpc call to uiautomator2 server
    
    Raises:
        UiAutomationError
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    r = _http_request(dev, "POST", "/jsonrpc/0", payload, timeout=timeout, print_request=print_request)
    data = r.json()
    if not isinstance(data, dict):
        raise RPCInvalidError("Unknown RPC error: not a dict")
    
    if isinstance(data, dict) and "error" in data:
        logger.debug("jsonrpc error: %s", data)
        code = data['error'].get('code')
        message = data['error'].get('message', '')
        stacktrace = data['error'].get('data')
        if "UiAutomation not connected" in r.text:
            raise UiAutomationNotConnectedError("UiAutomation not connected")
        if "android.os.DeadObjectException" in message:
            # https://developer.android.com/reference/android/os/DeadObjectException
            raise UiAutomationNotConnectedError("android.os.DeadObjectException")
        if "android.os.DeadSystemRuntimeException" in message:
            raise UiAutomationNotConnectedError("android.os.DeadSystemRuntimeException")
        if "uiautomator.UiObjectNotFoundException" in message:
            raise UiObjectNotFoundError(code, message, params)
        if "java.lang.StackOverflowError" in message:
            raise RPCStackOverflowError(f"StackOverflowError: {message}", params, stacktrace[:1000] + "..." + stacktrace[-1000:])
        raise RPCUnknownError(f"Unknown RPC error: {code} {message}", params, stacktrace)
    
    if "result" not in data:
        raise RPCInvalidError("Unknown RPC error: no result field")
    return data["result"]


class BasicUiautomatorServer(AbstractUiautomatorServer):
    """ Simple uiautomator2 server client
    this is runs without atx-agent
    """
    _lock = threading.Lock() # thread safe lock
    
    def __init__(self, dev: adbutils.AdbDevice) -> None:
        self._dev = dev
        self._process = None
        self._debug = False
        self.start_uiautomator()
        atexit.register(self.stop_uiautomator, wait=False)
    
    @property
    def debug(self) -> bool:
        return self._debug

    @debug.setter
    def debug(self, value: bool):
        self._debug = bool(value)

    def start_uiautomator(self):
        """
        Start uiautomator2 server

        Raises:
            LaunchUiautomatorError: uiautomator2 server not ready
        """
        with self._lock:
            self._setup_jar()
            if self._process:
                if self._process.pool() is not None:
                    self._process = None
            if not self._check_alive():
                self._process = launch_uiautomator(self._dev)
                self._wait_ready()

    def _setup_jar(self):
        assets_dir = Path(__file__).parent / "assets"
        jar_path = assets_dir / "u2.jar"
        target_path = "/data/local/tmp/u2.jar"
        if self._check_device_file_hash(jar_path, target_path):
            logger.debug("file u2.jar already pushed")
        else:
            logger.debug("push %s -> %s", jar_path, target_path)
            self._dev.sync.push(jar_path, target_path, check=True)
    
    def _check_device_file_hash(self, local_file: Union[str, Path], remote_file: str) -> bool:
        """ check if remote file hash is correct """
        md5 = hashlib.md5()
        with open(local_file, "rb") as f:
            md5.update(f.read())
        local_md5 = md5.hexdigest()
        logger.debug("file %s md5: %s", os.path.basename(local_file), local_md5)
        output = self._dev.shell(["toybox", "md5sum", remote_file])
        return local_md5 in output

    def _wait_ready(self, launch_timeout=30):
        """Wait until uiautomator2 server is ready"""
        self._wait_app_process_ready(launch_timeout)
    
    def _wait_app_process_ready(self, timeout: float):
        """
        ERROR1:
            [server] INFO: [UiAutomator2Server] Starting Server
            java.lang.IllegalStateException: UiAutomationService android.accessibilityservice.IAccessibilityServiceClient$Stub$Proxy@5deffd5already registered!

        NORMAL:
            [server] INFO: [UiAutomator2Server] Starting Server
            SLF4J: Failed to load class "org.slf4j.impl.StaticLoggerBinder".
            SLF4J: Defaulting to no-operation (NOP) logger implementation
            SLF4J: See http://www.slf4j.org/codes.html#StaticLoggerBinder for further details.
        """
        deadline = time.time() + timeout
        output_buffer = ''
        while time.time() < deadline:
            output = self._process.output.decode("utf-8", errors="ignore")
            output_buffer += output
            if "already registered" in output:
                raise AccessibilityServiceAlreadyRegisteredError(output)
            if self._process.pool() is not None:
                raise LaunchUiAutomationError("server quit unexpectly", output_buffer)
            if self._check_alive():
                return
            time.sleep(.5)
        raise LaunchUiAutomationError("server not ready", output_buffer)

    def _check_alive(self) -> bool:
        try:
            response = _http_request(self._dev, "GET", "/ping")
            return response.content == b"pong"
        except HTTPError:
            return False
    
    def stop_uiautomator(self, wait=True):
        with self._lock:
            if self._process:
                self._process.kill()
                self._process = None
        # wait server quit
        if wait:
            deadline = time.time() + 10
            while time.time() < deadline:
                if not self._check_alive():
                    return
                time.sleep(.5)

    def jsonrpc_call(self, method: str, params: Any = None, timeout: float = 10) -> Any:
        """Send jsonrpc call to uiautomator2 server"""
        try:
            return _jsonrpc_call(self._dev, method, params, timeout, self._debug)
        except (HTTPError, UiAutomationNotConnectedError) as e:
            logger.debug("uiautomator2 is not ok, error: %s", e)
            self.stop_uiautomator()
            self.start_uiautomator()
            return _jsonrpc_call(self._dev, method, params, timeout, self._debug)
