# coding: utf-8

from __future__ import absolute_import

import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import adbutils

import uiautomator2 as u2
from uiautomator2.agent_cli.protocol import SERVER_PROTOCOL_VERSION
from uiautomator2.core import DEFAULT_SERVER_PORT as DEFAULT_DEVICE_PORT

logger = logging.getLogger(__name__)

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _bounds_area(bounds_str: str) -> int:
    match = _BOUNDS_RE.fullmatch(bounds_str)
    if not match:
        return 0
    x1, y1, x2, y2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
    return max(0, x2 - x1) * max(0, y2 - y1)


def _is_invisible(node: ET.Element) -> bool:
    if node.get("displayed") == "false":
        return True
    bounds = node.get("bounds", "")
    return bool(bounds) and _bounds_area(bounds) == 0


def _has_content(node: ET.Element) -> bool:
    return bool(
        node.get("text", "").strip()
        or node.get("content-desc", "").strip()
        or node.get("resource-id", "").strip()
    )


def _is_interactive(node: ET.Element) -> bool:
    return node.get("clickable") == "true" or node.get("scrollable") == "true"


def _render_node(node: ET.Element, lines: List[str], depth: int):
    if _is_invisible(node):
        return

    children = list(node)
    if node.tag != "hierarchy" and not _has_content(node) and not _is_interactive(node) and len(children) == 1:
        _render_node(children[0], lines, depth)
        return

    parts = []

    class_name = node.get("class", node.tag)
    if class_name and class_name != "hierarchy":
        parts.append(class_name)

    text = node.get("text", "").strip()
    if text:
        parts.append('"%s"' % text)

    desc = node.get("content-desc", "").strip()
    if desc and desc != text:
        parts.append('desc="%s"' % desc)

    resource_id = node.get("resource-id", "").strip()
    if resource_id:
        parts.append("#%s" % resource_id)

    bounds = node.get("bounds", "")
    if bounds:
        match = _BOUNDS_RE.fullmatch(bounds)
        if match:
            parts.append("[%s,%s,%s,%s]" % (match.group(1), match.group(2), match.group(3), match.group(4)))

    flags = []
    if node.get("clickable") == "true":
        flags.append("click")
    if node.get("scrollable") == "true":
        flags.append("scroll")
    if node.get("checked") == "true":
        flags.append("checked")
    if node.get("focused") == "true":
        flags.append("focused")
    if node.get("selected") == "true":
        flags.append("selected")
    if node.get("enabled") == "false":
        flags.append("disabled")
    if flags:
        parts.append(" ".join(flags))

    if parts:
        lines.append("  " * depth + " ".join(parts))
        child_depth = depth + 1
    else:
        child_depth = depth

    for child in children:
        _render_node(child, lines, child_depth)


def hierarchy_to_text(xml: str) -> str:
    root = ET.fromstring(xml)
    lines = []
    _render_node(root, lines, 0)
    return "\n".join(lines)


class DeviceRegistry(object):
    def __init__(self, connector: Optional[Callable[..., u2.Device]] = None,
                 device_lister: Optional[Callable[[], List[str]]] = None,
                 default_serial_getter: Optional[Callable[[], str]] = None):
        self._connector = connector or u2.connect
        self._device_lister = device_lister or self._list_online_serials
        self._default_serial_getter = default_serial_getter or self._current_unique_serial
        self._devices = {}
        self._default_serial = None
        self._lock = threading.Lock()

    @property
    def default_serial(self) -> Optional[str]:
        return self._default_serial

    @staticmethod
    def _list_online_serials() -> List[str]:
        return [device.serial for device in adbutils.adb.device_list()]

    @staticmethod
    def _current_unique_serial() -> str:
        return adbutils.adb.device().serial

    def _resolve_default_serial(self, port: int) -> str:
        if self._default_serial is not None:
            online_serials = self._device_lister()
            if self._default_serial in online_serials:
                return self._default_serial

            logger.info("default device offline, clear cached device serial=%r", self._default_serial)
            self._devices.pop(("", port), None)
            self._default_serial = None

        self._default_serial = self._default_serial_getter()
        logger.info("bind default device serial=%r", self._default_serial)
        return self._default_serial

    def get(self, serial: Optional[str] = None, port: int = DEFAULT_DEVICE_PORT):
        device, _ = self.get_with_serial(serial, port=port)
        return device

    def get_with_serial(self, serial: Optional[str] = None, port: int = DEFAULT_DEVICE_PORT):
        with self._lock:
            connect_serial = serial
            if connect_serial is None:
                connect_serial = self._resolve_default_serial(port)
            key = (serial or "", port)
            if key not in self._devices:
                self._devices[key] = self._connector(connect_serial, port=port)
            return self._devices[key], connect_serial


class U2CliServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], registry: Optional[DeviceRegistry] = None):
        super(U2CliServer, self).__init__(server_address, U2CliRequestHandler)
        self.registry = registry or DeviceRegistry()


class U2CliRequestHandler(BaseHTTPRequestHandler):
    server: U2CliServer
    _REQUEST_HANDLERS = {
        "screenshot": "_screenshot",
        "dump_hierarchy": "_dump_hierarchy",
        "app_current": "_app_current",
        "device_info": "_device_info",
        "window_size": "_window_size",
        "app_start": "_app_start",
        "app_list": "_app_list",
        "app_stop": "_app_stop",
        "app_install": "_app_install",
        "app_uninstall": "_app_uninstall",
        "app_clear": "_app_clear",
        "shell": "_shell",
        "open_notification": "_open_notification",
        "open_quick_settings": "_open_quick_settings",
        "open_url": "_open_url",
        "press": "_press",
        "send_keys": "_send_keys",
        "clear_text": "_clear_text",
        "click": "_click",
        "double_click": "_double_click",
        "long_click": "_long_click",
        "swipe": "_swipe",
        "drag": "_drag",
        "selector_exists": "_selector_exists",
        "selector_wait": "_selector_wait",
        "selector_scroll": "_selector_scroll",
    }

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
            if payload.get("method") == "server.stop":
                self._send_json({"ok": True, "result": {"stopping": True}})
                threading.Thread(target=self.server.shutdown, name="u2cli_server_shutdown").start()
                return
            result = self._dispatch(payload.get("method"), payload.get("params") or {})
            self._send_json({"ok": True, "result": result})
        except Exception as e:
            logger.exception("u2cli request failed")
            self._send_json({"ok": False, "error": str(e), "type": e.__class__.__name__})

    def _dispatch(self, method: str, params: Dict[str, Any]):
        if method == "server.status":
            return self._status()

        handler_name = self._REQUEST_HANDLERS.get(method)
        if handler_name:
            return getattr(self, handler_name)(params)
        raise ValueError("unknown method: %s" % method)

    def _status(self):
        host, port = self.server.server_address[:2]
        return {
            "pid": os.getpid(),
            "host": host,
            "port": port,
            "protocol_version": SERVER_PROTOCOL_VERSION,
            "device_serial": self.server.registry.default_serial,
        }

    def _device(self, params: Dict[str, Any]):
        port = int(params.get("port") or DEFAULT_DEVICE_PORT)
        return self.server.registry.get_with_serial(params.get("serial"), port=port)

    def _screenshot(self, params: Dict[str, Any]):
        filename = params.get("filename")
        if not filename:
            raise ValueError("filename is required")
        device, device_serial = self._device(params)
        image = device.screenshot()
        width, height = image.size
        image.save(filename)
        return {"filename": filename, "resolution": "%sx%s" % (width, height), "device_serial": device_serial}

    def _dump_hierarchy(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)

        kwargs = {}
        if params.get("compressed"):
            kwargs["compressed"] = True
        if params.get("max_depth") is not None:
            kwargs["max_depth"] = int(params.get("max_depth"))

        xml = device.dump_hierarchy(**kwargs)
        result = xml if params.get("raw") else hierarchy_to_text(xml)
        output = params.get("output")
        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(result)
            return {"filename": output, "device_serial": device_serial}
        return {"content": result, "device_serial": device_serial}

    def _app_current(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        result = device.app_current()
        result["device_serial"] = device_serial
        return result

    def _device_info(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        result = dict(device.device_info)
        result["device_serial"] = device_serial
        return result

    def _window_size(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        width, height = device.window_size()
        return {"width": width, "height": height, "device_serial": device_serial}

    def _app_start(self, params: Dict[str, Any]):
        package = params.get("package")
        if not package:
            raise ValueError("package is required")
        device, device_serial = self._device(params)
        kwargs = {}
        if params.get("activity"):
            kwargs["activity"] = params.get("activity")
        if params.get("wait"):
            kwargs["wait"] = True
        if params.get("stop"):
            kwargs["stop"] = True
        device.app_start(package, **kwargs)
        return {"device_serial": device_serial}

    def _app_list(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        packages = device.app_list(params.get("filter") or "")
        return {"packages": packages, "device_serial": device_serial}

    def _app_stop(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        if params.get("all"):
            device.app_stop_all()
            return {"device_serial": device_serial}
        package = params.get("package")
        if not package:
            raise ValueError("package is required unless --all is used")
        device.app_stop(package)
        return {"device_serial": device_serial}

    def _app_install(self, params: Dict[str, Any]):
        apk = params.get("apk")
        if not apk:
            raise ValueError("apk is required")
        device, device_serial = self._device(params)
        result = device.app_install(apk)
        return {"result": result, "device_serial": device_serial}

    def _app_uninstall(self, params: Dict[str, Any]):
        package = params.get("package")
        if not package:
            raise ValueError("package is required")
        device, device_serial = self._device(params)
        result = device.app_uninstall(package)
        return {"result": result, "device_serial": device_serial}

    def _app_clear(self, params: Dict[str, Any]):
        package = params.get("package")
        if not package:
            raise ValueError("package is required")
        device, device_serial = self._device(params)
        device.app_clear(package)
        return {"device_serial": device_serial}

    def _shell(self, params: Dict[str, Any]):
        command = params.get("command")
        if not command:
            raise ValueError("command is required")
        device, device_serial = self._device(params)
        response = device.shell(command, timeout=int(params.get("timeout") or 60))
        return {"output": response.output, "exit_code": response.exit_code, "device_serial": device_serial}

    def _open_notification(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        device.open_notification()
        return {"device_serial": device_serial}

    def _open_quick_settings(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        device.open_quick_settings()
        return {"device_serial": device_serial}

    def _open_url(self, params: Dict[str, Any]):
        url = params.get("url")
        if not url:
            raise ValueError("url is required")
        device, device_serial = self._device(params)
        device.open_url(url)
        return {"device_serial": device_serial}

    def _press(self, params: Dict[str, Any]):
        key = params.get("key")
        if key is None:
            raise ValueError("key is required")
        device, device_serial = self._device(params)
        device.press(key)
        return {"device_serial": device_serial}

    def _send_keys(self, params: Dict[str, Any]):
        text = params.get("text")
        if text is None:
            raise ValueError("text is required")
        device, device_serial = self._device(params)
        device.send_keys(text, clear=bool(params.get("clear")))
        return {"device_serial": device_serial}

    def _clear_text(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        device.clear_text()
        return {"device_serial": device_serial}

    @staticmethod
    def _ui_object(device, params: Dict[str, Any]):
        selector = params.get("selector") or {}
        obj = device(**selector)
        child_selectors = []
        if params.get("child_selector"):
            child_selectors.append(params.get("child_selector"))
        child_selectors.extend(params.get("child_selectors") or [])
        for child_selector in child_selectors:
            obj = obj.child(**child_selector)
        return obj

    def _click(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        selector = params.get("selector") or {}
        if selector:
            self._ui_object(device, params).click(timeout=params.get("timeout"))
        else:
            device.click(float(params.get("x")), float(params.get("y")))
        return {"device_serial": device_serial}

    def _double_click(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        device.double_click(float(params.get("x")), float(params.get("y")), duration=float(params.get("duration") or 0.1))
        return {"device_serial": device_serial}

    def _long_click(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        selector = params.get("selector") or {}
        duration = float(params.get("duration") or 0.5)
        if selector:
            self._ui_object(device, params).long_click(duration=duration, timeout=params.get("timeout"))
        else:
            device.long_click(float(params.get("x")), float(params.get("y")), duration=duration)
        return {"device_serial": device_serial}

    def _swipe(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        kwargs = {}
        if params.get("steps") is not None:
            kwargs["steps"] = int(params.get("steps"))
        elif params.get("duration") is not None:
            kwargs["duration"] = float(params.get("duration"))
        if params.get("direction"):
            scale = params.get("scale")
            device.swipe_ext(params.get("direction"), scale=0.9 if scale is None else float(scale), **kwargs)
            return {"device_serial": device_serial}

        for name in ("fx", "fy", "tx", "ty"):
            if params.get(name) is None:
                raise ValueError("fx, fy, tx and ty are required")
        device.swipe(
            float(params.get("fx")),
            float(params.get("fy")),
            float(params.get("tx")),
            float(params.get("ty")),
            **kwargs,
        )
        return {"device_serial": device_serial}

    def _drag(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        device.drag(
            float(params.get("sx")),
            float(params.get("sy")),
            float(params.get("ex")),
            float(params.get("ey")),
            duration=float(params.get("duration") or 0.5),
        )
        return {"device_serial": device_serial}

    def _selector_exists(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        timeout = float(params.get("timeout") or 0)
        obj = self._ui_object(device, params)
        exists = obj.exists(timeout=timeout) if timeout else obj.exists
        return {"result": bool(exists), "device_serial": device_serial}

    def _selector_wait(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        obj = self._ui_object(device, params)
        timeout = float(params.get("timeout") or 3.0)
        if params.get("gone"):
            result = obj.wait_gone(timeout=timeout)
        else:
            result = obj.wait(timeout=timeout)
        return {"result": bool(result), "device_serial": device_serial}

    def _selector_scroll(self, params: Dict[str, Any]):
        device, device_serial = self._device(params)
        obj = self._ui_object(device, params)
        direction = params.get("direction") or "vert"
        action = params.get("action") or "forward"
        target = getattr(obj.scroll, direction)
        if params.get("to_text"):
            target.to(text=params.get("to_text"))
        elif params.get("max_swipes") is not None:
            getattr(target, action)(max_swipes=int(params.get("max_swipes")))
        else:
            getattr(target, action)()
        return {"device_serial": device_serial}

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
