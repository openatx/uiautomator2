# coding: utf-8

from __future__ import absolute_import

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

import uiautomator2 as u2
from uiautomator2.core import DEFAULT_SERVER_PORT as DEFAULT_DEVICE_PORT

logger = logging.getLogger(__name__)


class DeviceRegistry(object):
    def __init__(self, connector: Optional[Callable[..., u2.Device]] = None):
        self._connector = connector or u2.connect
        self._devices = {}
        self._lock = threading.Lock()

    def get(self, serial: Optional[str] = None, port: int = DEFAULT_DEVICE_PORT):
        key = (serial or "", port)
        with self._lock:
            if key not in self._devices:
                self._devices[key] = self._connector(serial, port=port)
            return self._devices[key]


class U2CliServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], registry: Optional[DeviceRegistry] = None):
        super(U2CliServer, self).__init__(server_address, U2CliRequestHandler)
        self.registry = registry or DeviceRegistry()


class U2CliRequestHandler(BaseHTTPRequestHandler):
    server: U2CliServer

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def do_GET(self):
        if self.path != "/status":
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        self._send_json({"ok": True, "result": self._status()})

    def do_POST(self):
        if self.path != "/request":
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return

        try:
            content_length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            result = self._dispatch(payload.get("method"), payload.get("params") or {})
            self._send_json({"ok": True, "result": result})
        except Exception as e:
            logger.exception("u2cli request failed")
            self._send_json({"ok": False, "error": str(e), "type": e.__class__.__name__})

    def _dispatch(self, method: str, params: Dict[str, Any]):
        if method == "server.status":
            return self._status()
        if method == "server.stop":
            threading.Thread(target=self.server.shutdown, name="u2cli_server_shutdown").start()
            return {"stopping": True}
        if method == "screenshot":
            return self._screenshot(params)
        raise ValueError("unknown method: %s" % method)

    def _status(self):
        host, port = self.server.server_address[:2]
        return {"pid": os.getpid(), "host": host, "port": port}

    def _screenshot(self, params: Dict[str, Any]):
        filename = params.get("filename")
        if not filename:
            raise ValueError("filename is required")
        port = int(params.get("port") or DEFAULT_DEVICE_PORT)
        device = self.server.registry.get(params.get("serial"), port=port)
        image = device.screenshot()
        width, height = image.size
        image.save(filename)
        return {"filename": filename, "resolution": "%sx%s" % (width, height)}

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str, port: int):
    httpd = U2CliServer((host, port))
    logger.info("u2cli server listening on %s:%d", host, port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
