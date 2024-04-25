#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Thu Apr 25 2024 14:50:05 by codeskyblue
"""

import atexit
import threading
import time
import logging
import json
from pathlib import Path
from typing import Any, Dict, Optional

import adbutils
import requests

from uiautomator2.exceptions import JSONRpcInvalidResponseError, UiAutomationNotConnectedError, HTTPError, LaunchUiautomatorError, UnknownRPCError, APkSignatureError
from uiautomator2.abstract import AbstractUiautomatorServer


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


def launch_uiautomator(dev: adbutils.AdbDevice) -> MockAdbProcess:
    """Launch uiautomator2 server on device"""
    logger.debug("launch uiautomator")
    dev.shell("am force-stop com.github.uiautomator")
    dev.shell("am start -n com.github.uiautomator/.ToastActivity")
    # use command to see if uiautomator is running: ps -A | grep uiautomator
    conn = dev.shell("am instrument -w -r -e debug false -e class com.github.uiautomator.stub.Stub com.github.uiautomator.test/androidx.test.runner.AndroidJUnitRunner", stream=True)
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
        url = f"http://localhost:{lport}{path}"
        if print_request:
            fields = [time.strftime("%H:%M:%S"), f"$ curl -X {method}", url]
            if data:
                fields.append(f"-d '{json.dumps(data)}'")
            print(f"# http timeout={timeout}")
            print(" ".join(fields))
        r = requests.request(method, url, json=data, timeout=timeout)
        r.raise_for_status()
        response = HTTPResponse(r.content)
        if print_request:
            print(f"{time.strftime('%H:%M:%S')} Response >>>")
            print(response.text)
            print(f"<<< END")
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
        raise JSONRpcInvalidResponseError("Unknown RPC error: not a dict")
    
    if isinstance(data, dict) and "error" in data:
        logger.debug("jsonrpc error: %s", data)
        code = data['error'].get('code')
        message = data['error'].get('message')
        if "UiAutomation not connected" in r.text:
            raise UiAutomationNotConnectedError("UiAutomation not connected")
        raise UnknownRPCError(f"Unknown RPC error: {code} {message}")
    
    if "result" not in data:
        raise JSONRpcInvalidResponseError("Unknown RPC error: no result field")
    return data["result"]



class BasicUiautomatorServer(AbstractUiautomatorServer):
    """ Simple uiautomator2 server client
    this is runs without atx-agent
    """
    def __init__(self, dev: adbutils.AdbDevice) -> None:
        self._dev = dev
        self._process = None
        self._lock = threading.Lock()
        self._debug = False
        atexit.register(self.stop_uiautomator)
    
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
            self._setup_apks()
            if self._process:
                if self._process.pool() is not None:
                    self._process = None
            self._process = launch_uiautomator(self._dev)
            self._wait_ready()
    
    def _setup_apks(self):
        assets_dir = Path(__file__).parent / "assets"
        main_apk = assets_dir / "app-uiautomator.apk"
        test_apk = assets_dir / "app-uiautomator-test.apk"

        # get apk version
        version_text = assets_dir / "version.txt"
        apk_version = None
        for line in version_text.read_text('utf-8').splitlines():
            k, v = line.split(":")
            if k == "apk_version":
                apk_version = v.strip()
                break
        logger.debug("apk_version: %s", apk_version)
        # install apk when not installed or version not match, dev version always keep
        main_apk_info = self._dev.app_info("com.github.uiautomator")
        if main_apk_info is None:
            self._install_apk(main_apk)
        elif main_apk_info.version_name != apk_version and "dev" in main_apk_info.version_name:
            self._install_apk(main_apk)
            self._install_apk(test_apk)

        if self._dev.app_info("com.github.uiautomator.test") is None:
            self._install_apk(test_apk)
    
    def _install_apk(self, apk_path: Path):
        logger.debug("Install %s", apk_path)
        self._dev.shell("mkdir -p /data/local/tmp/u2")
        target_path = "/data/local/tmp/u2/" + apk_path.name
        self._dev.push(apk_path, target_path)
        self._dev.shell(['pm', 'install', '-r', '-t', target_path])
    
    def _wait_instrument_ready(self, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            output = self._process.output.decode("utf-8", errors="ignore")
            if "does not have a signature matching the target" in output:
                raise APkSignatureError("app-uiautomator.apk does not have a signature matching the target")
            if "INSTRUMENTATION_STATUS: Error=" in output:
                error_message = output[output.find("INSTRUMENTATION_STATUS: Error="):].splitlines()[0]
                raise LaunchUiautomatorError(error_message, output)
            if "INSTRUMENTATION_STATUS_CODE: -1" in output:
                raise LaunchUiautomatorError("am instrument error", output)
            if "INSTRUMENTATION_STATUS_CODE: 1" in output:
                # success
                return
            time.sleep(.5)
        raise LaunchUiautomatorError("am instrument timeout")
    
    def _wait_stub_ready(self, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                response = _http_request(self._dev, "GET", "/ping")
                if response.content == b"pong":            
                    return
            except HTTPError:
                time.sleep(.5)
        raise LaunchUiautomatorError("uiautomator2 server not ready")
        
    def _wait_ready(self, launch_timeout=10, service_timeout=30):
        """Wait until uiautomator2 server is ready"""
        # wait am instrument start
        self._wait_instrument_ready(launch_timeout)
        # launch a toast window to make sure uiautomator is alive
        logger.debug("show float window")
        self._dev.shell("am start -n com.github.uiautomator/.ToastActivity -e showFloatWindow true")
        self._wait_stub_ready(service_timeout)
    
    def stop_uiautomator(self):
        with self._lock:
            if self._process:
                self._process.kill()
                self._process = None

    def jsonrpc_call(self, method: str, params: Any = None, timeout: float = 10) -> Any:
        """Send jsonrpc call to uiautomator2 server"""
        try:
            return _jsonrpc_call(self._dev, method, params, timeout, self._debug)
        except (HTTPError, UiAutomationNotConnectedError) as e:
            logger.debug("uiautomator2 is not ok, error: %s", e)
            try:
                self.start_uiautomator()
            except APkSignatureError as e:
                logger.debug("APkSignatureError: %s", e)
                self._dev.uninstall("com.github.uiautomator")
                self._dev.uninstall("com.github.uiautomator.test")
                self.start_uiautomator()
            return _jsonrpc_call(self._dev, method, params, timeout, self._debug)


class SimpleUiautomatorServer(BasicUiautomatorServer, AbstractUiautomatorServer):
    @property
    def info(self) -> Dict[str, Any]:
        return self.jsonrpc_call("deviceInfo")
    
    def dump_hierarchy(self, compressed: bool = False, pretty: bool = False) -> str:
        return self.jsonrpc_call("dumpWindowHierarchy", [compressed, pretty])
