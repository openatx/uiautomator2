# coding: utf-8

from __future__ import absolute_import

import json
import os
import subprocess
import sys
import time
from http.client import IncompleteRead
from typing import Any, Dict, Optional, Tuple
from urllib import error, request

from uiautomator2.agent_cli.protocol import SERVER_PROTOCOL_VERSION

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 17913
DEFAULT_REQUEST_TIMEOUT = 30.0


class U2CliError(RuntimeError):
    """Base error for u2cli client operations."""


class ServerNotRunningError(U2CliError):
    """Raised when the local u2cli server is not reachable."""


class RemoteError(U2CliError):
    """Raised when the local u2cli server returns an error response."""


class U2CliClient(object):
    def __init__(self, host: str = DEFAULT_SERVER_HOST, port: int = DEFAULT_SERVER_PORT):
        self.host = host
        self.port = port

    @property
    def base_url(self) -> str:
        return "http://%s:%d" % (self.host, self.port)

    def _server_not_running(self, exc: BaseException) -> ServerNotRunningError:
        return ServerNotRunningError("u2cli server is not running at %s: %s" % (self.base_url, exc))

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = DEFAULT_REQUEST_TIMEOUT):
        payload = json.dumps({"method": method, "params": params or {}}).encode("utf-8")
        req = request.Request(
            self.base_url + "/request",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (error.URLError, OSError, IncompleteRead) as e:
            raise self._server_not_running(e) from e
        except ValueError as e:
            raise U2CliError("invalid response from u2cli server at %s: %s" % (self.base_url, e)) from e

        if not data.get("ok"):
            raise RemoteError(data.get("error") or "unknown u2cli server error")
        return data.get("result")

    def status(self, timeout: float = 2.0):
        return self.request("server.status", timeout=timeout)

    def is_running(self) -> bool:
        try:
            self.status()
            return True
        except U2CliError:
            return False


def start_server_process(host: str = DEFAULT_SERVER_HOST, port: int = DEFAULT_SERVER_PORT) -> subprocess.Popen:
    command = [
        sys.executable,
        "-m",
        "uiautomator2.agent_cli",
        "--server-host",
        host,
        "--server-port",
        str(port),
        "server",
        "--foreground",
    ]
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) |
            getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _server_is_compatible(status: Dict[str, Any]) -> bool:
    return status.get("protocol_version") == SERVER_PROTOCOL_VERSION


def _stop_server(client: U2CliClient, timeout: float):
    try:
        client.request("server.stop", timeout=2.0)
    except U2CliError:
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not client.is_running():
            return
        time.sleep(0.1)
    raise U2CliError("incompatible u2cli server did not stop")


def ensure_server(host: str = DEFAULT_SERVER_HOST, port: int = DEFAULT_SERVER_PORT,
                  timeout: float = 5.0) -> Tuple[U2CliClient, bool]:
    client = U2CliClient(host, port)
    try:
        status = client.status()
    except U2CliError:
        pass
    else:
        if _server_is_compatible(status):
            return client, False
        _stop_server(client, timeout)

    process = start_server_process(host, port)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.is_running():
            return client, True
        if process.poll() is not None:
            raise U2CliError("u2cli server exited before it became ready")
        time.sleep(0.1)
    raise U2CliError("u2cli server did not become ready")
