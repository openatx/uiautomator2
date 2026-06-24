# coding: utf-8

from __future__ import absolute_import, print_function

import argparse
import logging
import pathlib
import sys
from typing import Any, Dict, Optional

from PIL import Image

from uiautomator2 import enable_pretty_logging
from uiautomator2.agent_cli.client import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT, U2CliClient, U2CliError, \
    ensure_server
from uiautomator2.agent_cli.server import run_server
from uiautomator2.core import DEFAULT_SERVER_PORT as DEFAULT_DEVICE_PORT
from uiautomator2.core import check_port

logger = logging.getLogger(__name__)


class U2CliArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        _output_error_message(message, "ArgumentError")
        self.exit(2)


def _valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("port must be an integer, got %r" % value)
    try:
        check_port(port)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    return port


def _absolute_filename(filename: str) -> str:
    path = pathlib.Path(filename).expanduser()
    if not path.is_absolute():
        path = pathlib.Path.cwd() / path
    return str(path)


def _output_result(result: Any = None, u2_code: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
    device_serial = extra.get("device_serial") if extra else None
    if device_serial is None and isinstance(result, dict):
        device_serial = result.get("device_serial")
    if device_serial:
        print("device_serial: %s" % device_serial)
    if u2_code:
        print("u2_code: %s" % u2_code)
    if extra:
        for key, value in extra.items():
            if key == "device_serial":
                continue
            print("%s: %s" % (key, value))
    if result is not None:
        if isinstance(result, dict):
            for key, value in result.items():
                if key == "device_serial":
                    continue
                print("%s: %s" % (key, value))
        elif isinstance(result, list):
            for value in result:
                print(value)
        elif isinstance(result, str) and "\n" in result:
            _output_text(result)
        else:
            print("result: %s" % result)


def _output_text(result: str):
    sys.stdout.write(result)
    if not result.endswith("\n"):
        sys.stdout.write("\n")


def _output_text_result(result: str, u2_code: Optional[str] = None):
    if u2_code:
        print("u2_code: %s" % u2_code)
    if result:
        _output_text(result)


def _output_message(message: str, ok: bool = True, extra: Optional[Dict[str, Any]] = None):
    print(message)
    if extra:
        for key, value in extra.items():
            print("%s: %s" % (key, value))


def _output_error(exc: BaseException):
    _output_error_message(str(exc), exc.__class__.__name__)


def _output_error_message(message: str, error_type: str):
    print("error: %s" % message, file=sys.stderr)


def _image_resolution(filename: str) -> Optional[str]:
    try:
        with Image.open(filename) as image:
            width, height = image.size
    except OSError:
        return None
    return "%sx%s" % (width, height)


_SELECTOR_OPTIONS = [
    ("--text", "text"),
    ("--text-contains", "textContains"),
    ("--text-matches", "textMatches"),
    ("--text-starts-with", "textStartsWith"),
    ("--resource-id", "resourceId"),
    ("--class-name", "className"),
    ("--description", "description"),
    ("--description-contains", "descriptionContains"),
    ("--package", "packageName"),
    ("--index", "index"),
    ("--instance", "instance"),
    ("--checkable", "checkable"),
    ("--checked", "checked"),
    ("--clickable", "clickable"),
    ("--scrollable", "scrollable"),
    ("--enabled", "enabled"),
    ("--focused", "focused"),
    ("--selected", "selected"),
]

_BOOLEAN_SELECTOR_KEYS = {"checkable", "checked", "clickable", "scrollable", "enabled", "focused", "selected"}
_INTEGER_SELECTOR_KEYS = {"index", "instance"}


def _selector_name_map() -> Dict[str, str]:
    result = {}
    for option, u2_name in _SELECTOR_OPTIONS:
        option_name = option[2:]
        result[option_name] = u2_name
        result[option_name.replace("-", "_")] = u2_name
        result[u2_name] = u2_name
    return result


_SELECTOR_NAME_MAP = _selector_name_map()


def _selector_kwargs(args, prefix: str = "") -> Dict[str, Any]:
    result = {}
    for option, u2_name in _SELECTOR_OPTIONS:
        value = getattr(args, prefix + option.lstrip("-").replace("-", "_"), None)
        if value is not None and value is not False:
            result[u2_name] = value
    return result


def _parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise U2CliError("invalid boolean selector value: %s" % value)


def _parse_selector_token(token: str) -> tuple:
    if "=" in token:
        key, value = token.split("=", 1)
    else:
        key, value = token, "true"
    key = key.strip()
    if key not in _SELECTOR_NAME_MAP:
        raise U2CliError("unknown selector key: %s" % key)
    u2_name = _SELECTOR_NAME_MAP[key]
    if u2_name in _INTEGER_SELECTOR_KEYS:
        value = int(value)
    elif u2_name in _BOOLEAN_SELECTOR_KEYS:
        value = _parse_bool(value)
    return u2_name, value


def _child_selectors(args) -> list:
    result = []
    legacy_child = _selector_kwargs(args, prefix="child_")
    if legacy_child:
        result.append(legacy_child)
    for group in getattr(args, "child", None) or []:
        child = {}
        for token in group:
            key, value = _parse_selector_token(token)
            child[key] = value
        if child:
            result.append(child)
    return result


def _selector_chain(args):
    selector = _selector_kwargs(args)
    child_selectors = _child_selectors(args)
    if child_selectors and not selector:
        raise U2CliError("at least one parent selector option is required when child selector is used")
    return selector, child_selectors


def _selector_chain_payload(selector: Dict[str, Any], child_selectors: list) -> Dict[str, Any]:
    payload = {"selector": selector}
    if child_selectors:
        payload["child_selectors"] = child_selectors
    return payload


def _selector_repr(selector: Dict[str, Any]) -> str:
    return ", ".join("%s=%r" % (key, value) for key, value in selector.items())


def _selector_chain_code(selector: Dict[str, Any], child_selectors: list) -> str:
    code = "d(%s)" % _selector_repr(selector)
    for child_selector in child_selectors:
        code += ".child(%s)" % _selector_repr(child_selector)
    return code


def _require_selector(selector: Dict[str, Any]):
    if not selector:
        raise U2CliError("at least one selector option is required")


def _selector_option_kwargs(option: str) -> Dict[str, Any]:
    kwargs = {"default": None}
    if option in ("--index", "--instance"):
        kwargs["type"] = int
    if option in ("--checkable", "--checked", "--clickable", "--scrollable", "--enabled", "--focused", "--selected"):
        kwargs["action"] = "store_true"
    return kwargs


def _add_selector_flags(parser):
    selector_group = parser.add_argument_group("selector options")
    for option, _ in _SELECTOR_OPTIONS:
        selector_group.add_argument(option, **_selector_option_kwargs(option))

    child_group = parser.add_argument_group("child selector options")
    for option, _ in _SELECTOR_OPTIONS:
        child_group.add_argument("--child-" + option[2:], **_selector_option_kwargs(option))
    child_group.add_argument(
        "--child",
        action="append",
        default=None,
        nargs="+",
        metavar="KEY=VALUE",
        help="append a child selector level, e.g. --child text=OK resourceId=pkg:id/ok",
    )


def _add_server_flags(parser):
    group = parser.add_argument_group("server options")
    group.add_argument("--server-host", default=DEFAULT_SERVER_HOST, help="u2cli server listen host")
    group.add_argument("--server-port", type=_valid_port, default=DEFAULT_SERVER_PORT, help="u2cli server listen port")


def _add_device_flags(parser):
    group = parser.add_argument_group("device options")
    group.add_argument("-p", "--port", type=_valid_port, default=DEFAULT_DEVICE_PORT,
                       help="uiautomator2 server port on device (1-65535)")


def _add_command_flags(parser, command: Dict[str, Any]):
    if not command.get("flags"):
        return
    group = parser.add_argument_group("command options")
    for flag in command.get("flags", []):
        kwargs = flag.copy()
        args = kwargs.pop("args")
        group.add_argument(*args, **kwargs)


def cmd_server(args):
    run_server(args.server_host, args.server_port)


def cmd_start_server(args):
    _, started = ensure_server(args.server_host, args.server_port)
    if started:
        message = "u2cli server started"
    else:
        message = "u2cli server is already running"
    _output_message(message, extra={"host": args.server_host, "port": args.server_port})


def cmd_kill_server(args):
    client = U2CliClient(args.server_host, args.server_port)
    if not client.is_running():
        _output_message("u2cli server is not running")
        return
    client.request("server.stop", timeout=2.0)
    _output_message("u2cli server stopped")


def cmd_server_status(args):
    client = U2CliClient(args.server_host, args.server_port)
    if not client.is_running():
        status = {"running": False, "host": args.server_host, "port": args.server_port}
        _output_result(status)
        return
    status = client.status()
    status["running"] = True
    _output_result(status)


def cmd_screenshot(args):
    client, _ = ensure_server(args.server_host, args.server_port)
    abs_filename = _absolute_filename(args.filename)
    result = client.request("screenshot", {
        "serial": args.serial,
        "port": args.port,
        "filename": abs_filename,
    })
    saved_to = result.get("filename") if isinstance(result, dict) else abs_filename
    resolution = result.get("resolution") if isinstance(result, dict) else None
    device_serial = result.get("device_serial") if isinstance(result, dict) else args.serial
    if not resolution:
        resolution = _image_resolution(saved_to)
    extra = {"saved_to": saved_to}
    if device_serial:
        extra["device_serial"] = device_serial
    if resolution:
        extra["resolution"] = resolution
    _output_result(
        u2_code="d.screenshot(%r)" % args.filename,
        extra=extra,
    )


def _dump_hierarchy_u2_code(args) -> str:
    parts = []
    if args.compressed:
        parts.append("compressed=True")
    if args.max_depth is not None:
        parts.append("max_depth=%s" % args.max_depth)
    return "d.dump_hierarchy(%s)" % ", ".join(parts)


def cmd_dump_hierarchy(args):
    client, _ = ensure_server(args.server_host, args.server_port)
    output = _absolute_filename(args.output) if args.output else None
    result = client.request("dump_hierarchy", {
        "serial": args.serial,
        "port": args.port,
        "compressed": args.compressed,
        "max_depth": args.max_depth,
        "raw": args.raw,
        "output": output,
    })
    u2_code = _dump_hierarchy_u2_code(args)
    device_serial = result.get("device_serial") if isinstance(result, dict) else args.serial
    if output:
        saved_to = result.get("filename") if isinstance(result, dict) else output
        extra = {"saved_to": saved_to}
        if device_serial:
            extra["device_serial"] = device_serial
        _output_result(u2_code=u2_code, extra=extra)
        return

    content = result.get("content") if isinstance(result, dict) else result
    _output_result(u2_code=u2_code, extra={"device_serial": device_serial} if device_serial else None)
    if content:
        _output_text(content)


def cmd_app_current(args):
    client, _ = ensure_server(args.server_host, args.server_port)
    result = client.request("app_current", {
        "serial": args.serial,
        "port": args.port,
    })
    _output_result(result, u2_code="d.app_current()")


def _request_device_method(args, method: str, params: Optional[Dict[str, Any]] = None):
    client, _ = ensure_server(args.server_host, args.server_port)
    payload = {"serial": args.serial, "port": args.port}
    if params:
        payload.update(params)
    return client.request(method, payload)


def cmd_device_info(args):
    result = _request_device_method(args, "device_info")
    _output_result(result, u2_code="d.device_info")


def cmd_window_size(args):
    result = _request_device_method(args, "window_size")
    _output_result(result, u2_code="d.window_size()")


def cmd_app_start(args):
    params = {
        "package": args.package,
        "activity": args.activity,
        "wait": args.wait,
        "stop": args.stop,
    }
    result = _request_device_method(args, "app_start", params)
    parts = [repr(args.package)]
    if args.activity:
        parts.append("activity=%r" % args.activity)
    if args.wait:
        parts.append("wait=True")
    if args.stop:
        parts.append("stop=True")
    _output_result(result, u2_code="d.app_start(%s)" % ", ".join(parts))


def cmd_app_list(args):
    result = _request_device_method(args, "app_list", {"filter": args.filter})
    packages = result.get("packages") if isinstance(result, dict) else result
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    if args.filter:
        u2_code = "d.app_list(%r)" % args.filter
    else:
        u2_code = "d.app_list()"
    _output_result(packages, u2_code=u2_code, extra=extra)


def cmd_app_stop(args):
    if not args.all and not args.package:
        raise U2CliError("package is required unless --all is used")
    result = _request_device_method(args, "app_stop", {"package": args.package, "all": args.all})
    if args.all:
        u2_code = "d.app_stop_all()"
    else:
        u2_code = "d.app_stop(%r)" % args.package
    _output_result(result, u2_code=u2_code)


def cmd_app_install(args):
    result = _request_device_method(args, "app_install", {"apk": args.apk})
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    install_result = result.get("result") if isinstance(result, dict) else result
    _output_result(install_result, u2_code="d.app_install(%r)" % args.apk, extra=extra)


def cmd_app_uninstall(args):
    result = _request_device_method(args, "app_uninstall", {"package": args.package})
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    uninstall_result = result.get("result") if isinstance(result, dict) else result
    _output_result(uninstall_result, u2_code="d.app_uninstall(%r)" % args.package, extra=extra)


def cmd_app_clear(args):
    result = _request_device_method(args, "app_clear", {"package": args.package})
    _output_result(result, u2_code="d.app_clear(%r)" % args.package)


def cmd_shell(args):
    command = " ".join(args.cmd)
    result = _request_device_method(args, "shell", {"command": command, "timeout": args.timeout})
    output = result.get("output") if isinstance(result, dict) else result
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    if isinstance(result, dict) and result.get("exit_code") is not None:
        extra["exit_code"] = result.get("exit_code")
    _output_result(output, u2_code="d.shell(%r, timeout=%s)" % (command, args.timeout), extra=extra)


def cmd_open_notification(args):
    result = _request_device_method(args, "open_notification")
    _output_result(result, u2_code="d.open_notification()")


def cmd_open_quick_settings(args):
    result = _request_device_method(args, "open_quick_settings")
    _output_result(result, u2_code="d.open_quick_settings()")


def cmd_open_url(args):
    result = _request_device_method(args, "open_url", {"url": args.url})
    _output_result(result, u2_code="d.open_url(%r)" % args.url)


def _parse_key(key: str):
    try:
        return int(key)
    except ValueError:
        return key


def cmd_press(args):
    key = _parse_key(args.key)
    result = _request_device_method(args, "press", {"key": key})
    if isinstance(key, int):
        u2_code = "d.press(%s)" % key
    else:
        u2_code = "d.press(%r)" % key
    _output_result(result, u2_code=u2_code)


def cmd_send_keys(args):
    clear = not args.no_clear
    result = _request_device_method(args, "send_keys", {"text": args.text, "clear": clear})
    _output_result(result, u2_code="d.send_keys(%r, clear=%s)" % (args.text, clear))


def cmd_clear_text(args):
    result = _request_device_method(args, "clear_text")
    _output_result(result, u2_code="d.clear_text()")


def _optional_float(value):
    return None if value is None else float(value)


_SWIPE_DIRECTION_ALIASES = {
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
    "forward": "up",
    "backward": "down",
    "horiz-forward": "left",
    "horiz-backward": "right",
}


def _normalize_swipe_direction(value: str) -> Optional[str]:
    return _SWIPE_DIRECTION_ALIASES.get(value.lower().replace("_", "-"))


def _parse_swipe_fx(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        directions = ", ".join(sorted(_SWIPE_DIRECTION_ALIASES))
        raise U2CliError("swipe direction must be one of %s, or provide four coordinates" % directions)


def cmd_click(args):
    selector, child_selectors = _selector_chain(args)
    x, y = _optional_float(args.x), _optional_float(args.y)
    if selector:
        payload = _selector_chain_payload(selector, child_selectors)
        payload["timeout"] = args.timeout
        result = _request_device_method(args, "click", payload)
        u2_code = "%s.click(timeout=%s)" % (_selector_chain_code(selector, child_selectors), args.timeout)
    else:
        if x is None or y is None:
            raise U2CliError("x and y are required when no selector option is used")
        result = _request_device_method(args, "click", {"x": x, "y": y})
        u2_code = "d.click(%s, %s)" % (x, y)
    _output_result(result, u2_code=u2_code)


def cmd_double_click(args):
    result = _request_device_method(args, "double_click", {
        "x": args.x,
        "y": args.y,
        "duration": args.duration,
    })
    _output_result(result, u2_code="d.double_click(%s, %s, duration=%s)" % (args.x, args.y, args.duration))


def cmd_long_click(args):
    selector, child_selectors = _selector_chain(args)
    x, y = _optional_float(args.x), _optional_float(args.y)
    if selector:
        payload = _selector_chain_payload(selector, child_selectors)
        payload.update({
            "duration": args.duration,
            "timeout": args.timeout,
        })
        result = _request_device_method(args, "long_click", payload)
        u2_code = "%s.long_click(duration=%s, timeout=%s)" % (_selector_chain_code(selector, child_selectors), args.duration, args.timeout)
    else:
        if x is None or y is None:
            raise U2CliError("x and y are required when no selector option is used")
        result = _request_device_method(args, "long_click", {"x": x, "y": y, "duration": args.duration})
        u2_code = "d.long_click(%s, %s, duration=%s)" % (x, y, args.duration)
    _output_result(result, u2_code=u2_code)


def cmd_swipe(args):
    direction = _normalize_swipe_direction(args.fx)
    if direction:
        if args.fy is not None or args.tx is not None or args.ty is not None:
            raise U2CliError("coordinate arguments are not allowed when swipe direction is used")
        params = {"direction": direction, "scale": args.scale, "duration": args.duration, "steps": args.steps}
        result = _request_device_method(args, "swipe", params)
        if args.steps is not None:
            u2_code = "d.swipe_ext(%r, scale=%s, steps=%s)" % (direction, args.scale, args.steps)
        else:
            u2_code = "d.swipe_ext(%r, scale=%s, duration=%s)" % (direction, args.scale, args.duration)
        _output_result(result, u2_code=u2_code)
        return

    if args.fy is None or args.tx is None or args.ty is None:
        raise U2CliError("fx, fy, tx and ty are required when swipe direction is not used")
    if args.scale != 0.9:
        raise U2CliError("--scale is only supported when swipe direction is used")

    fx = _parse_swipe_fx(args.fx)
    params = {"fx": fx, "fy": args.fy, "tx": args.tx, "ty": args.ty, "duration": args.duration, "steps": args.steps}
    result = _request_device_method(args, "swipe", params)
    if args.steps is not None:
        u2_code = "d.swipe(%s, %s, %s, %s, steps=%s)" % (fx, args.fy, args.tx, args.ty, args.steps)
    else:
        u2_code = "d.swipe(%s, %s, %s, %s, duration=%s)" % (fx, args.fy, args.tx, args.ty, args.duration)
    _output_result(result, u2_code=u2_code)


def cmd_drag(args):
    result = _request_device_method(args, "drag", {
        "sx": args.sx,
        "sy": args.sy,
        "ex": args.ex,
        "ey": args.ey,
        "duration": args.duration,
    })
    _output_result(result, u2_code="d.drag(%s, %s, %s, %s, duration=%s)" % (args.sx, args.sy, args.ex, args.ey, args.duration))


def cmd_exists(args):
    selector, child_selectors = _selector_chain(args)
    _require_selector(selector)
    payload = _selector_chain_payload(selector, child_selectors)
    payload["timeout"] = args.timeout
    result = _request_device_method(args, "selector_exists", payload)
    if args.timeout:
        u2_code = "%s.exists(timeout=%s)" % (_selector_chain_code(selector, child_selectors), args.timeout)
    else:
        u2_code = "%s.exists" % _selector_chain_code(selector, child_selectors)
    device_serial = result.get("device_serial") if isinstance(result, dict) else None
    exists = result.get("result") if isinstance(result, dict) else result
    _output_result(exists, u2_code=u2_code, extra={"device_serial": device_serial} if device_serial else None)


def cmd_wait(args):
    selector, child_selectors = _selector_chain(args)
    _require_selector(selector)
    payload = _selector_chain_payload(selector, child_selectors)
    payload.update({"timeout": args.timeout, "gone": args.gone})
    result = _request_device_method(args, "selector_wait", payload)
    if args.gone:
        u2_code = "%s.wait_gone(timeout=%s)" % (_selector_chain_code(selector, child_selectors), args.timeout)
    else:
        u2_code = "%s.wait(timeout=%s)" % (_selector_chain_code(selector, child_selectors), args.timeout)
    device_serial = result.get("device_serial") if isinstance(result, dict) else None
    wait_result = result.get("result") if isinstance(result, dict) else result
    _output_result(wait_result, u2_code=u2_code, extra={"device_serial": device_serial} if device_serial else None)


def cmd_scroll(args):
    selector, child_selectors = _selector_chain(args)
    _require_selector(selector)
    payload = _selector_chain_payload(selector, child_selectors)
    payload.update({
        "direction": args.direction,
        "action": args.action,
        "max_swipes": args.max_swipes,
        "to_text": args.to_text,
    })
    result = _request_device_method(args, "selector_scroll", payload)
    if args.to_text:
        u2_code = "%s.scroll.%s.to(text=%r)" % (_selector_chain_code(selector, child_selectors), args.direction, args.to_text)
    elif args.max_swipes is not None:
        u2_code = "%s.scroll.%s.%s(max_swipes=%s)" % (_selector_chain_code(selector, child_selectors), args.direction, args.action, args.max_swipes)
    else:
        u2_code = "%s.scroll.%s.%s()" % (_selector_chain_code(selector, child_selectors), args.direction, args.action)
    _output_result(result, u2_code=u2_code)


_commands = [
    {"action": cmd_server, "command": "server", "help": "run u2cli server in foreground", "server": True,
     "flags": [{"args": ["--foreground"], "action": "store_true", "help": argparse.SUPPRESS}]},
    {"action": cmd_start_server, "command": "start-server", "help": "start u2cli server", "server": True},
    {"action": cmd_kill_server, "command": "kill-server", "help": "stop u2cli server", "server": True},
    {"action": cmd_server_status, "command": "server-status", "help": "show u2cli server status", "server": True},
    {
        "action": cmd_screenshot,
        "command": "screenshot",
        "help": "take device screenshot",
        "flags": [
            {
                "args": ["filename"],
                "nargs": "?",
                "default": "screenshot.jpg",
                "type": str,
                "help": "output filename, jpg or png",
            }
        ],
    },
    {
        "action": cmd_dump_hierarchy,
        "command": "dump-hierarchy",
        "help": "dump UI hierarchy",
        "flags": [
            {"args": ["--compressed"], "action": "store_true", "help": "use compressed hierarchy"},
            {"args": ["--max-depth"], "default": None, "type": int, "help": "maximum hierarchy depth"},
            {"args": ["--output", "-o"], "default": None, "help": "save output to file"},
            {"args": ["--raw"], "action": "store_true", "help": "output raw XML without simplification"},
        ],
    },
    {"action": cmd_app_current, "command": "app-current", "aliases": ["app_current"],
     "help": "show current foreground app"},
    {"action": cmd_device_info, "command": "device-info", "aliases": ["device_info"],
     "help": "show device information"},
    {"action": cmd_window_size, "command": "window-size", "aliases": ["window_size"],
     "help": "show screen window size"},
    {
        "action": cmd_app_start,
        "command": "app-start",
        "aliases": ["app_start"],
        "help": "start application",
        "flags": [
            {"args": ["--activity"], "default": None, "help": "specific activity to launch"},
            {"args": ["--wait"], "action": "store_true", "help": "wait for app to launch"},
            {"args": ["--stop"], "action": "store_true", "help": "stop app before launching"},
            {"args": ["package"], "help": "package name"},
        ],
    },
    {
        "action": cmd_app_list,
        "command": "app-list",
        "aliases": ["app_list"],
        "help": "list installed packages",
        "flags": [{"args": ["--filter"], "default": "", "help": "filter string passed to pm list packages"}],
    },
    {
        "action": cmd_app_stop,
        "command": "app-stop",
        "aliases": ["app_stop"],
        "help": "stop application",
        "flags": [
            {"args": ["--all"], "action": "store_true", "help": "stop all third-party apps"},
            {"args": ["package"], "nargs": "?", "help": "package name"},
        ],
    },
    {"action": cmd_app_install, "command": "app-install", "aliases": ["app_install"],
     "help": "install application", "flags": [{"args": ["apk"], "help": "apk path or url"}]},
    {"action": cmd_app_uninstall, "command": "app-uninstall", "aliases": ["app_uninstall"],
     "help": "uninstall application", "flags": [{"args": ["package"], "help": "package name"}]},
    {"action": cmd_app_clear, "command": "app-clear", "aliases": ["app_clear"],
     "help": "clear application data", "flags": [{"args": ["package"], "help": "package name"}]},
    {
        "action": cmd_shell,
        "command": "shell",
        "help": "run shell command",
        "flags": [
            {"args": ["--timeout"], "default": 60, "type": int, "help": "command timeout in seconds"},
            {"args": ["cmd"], "nargs": "+", "help": "shell command"},
        ],
    },
    {"action": cmd_open_notification, "command": "open-notification", "aliases": ["open_notification"],
     "help": "open notification shade"},
    {"action": cmd_open_quick_settings, "command": "open-quick-settings", "aliases": ["open_quick_settings"],
     "help": "open quick settings"},
    {"action": cmd_open_url, "command": "open-url", "aliases": ["open_url"],
     "help": "open url", "flags": [{"args": ["url"], "help": "url to open"}]},
    {"action": cmd_press, "command": "press", "help": "press key",
     "flags": [{"args": ["key"], "help": "key name or key code"}]},
    {"action": cmd_send_keys, "command": "send-keys", "aliases": ["send_keys"],
     "help": "type text into focused input",
     "flags": [
         {"args": ["--no-clear"], "action": "store_true", "help": "do not clear before typing"},
         {"args": ["text"], "help": "text to type"},
     ]},
    {"action": cmd_clear_text, "command": "clear-text", "aliases": ["clear_text"],
     "help": "clear focused input text"},
    {
        "action": cmd_click,
        "command": "click",
        "help": "click coordinates or selector",
        "selector": True,
        "flags": [
            {"args": ["--timeout"], "default": 3.0, "type": float, "help": "selector wait timeout"},
            {"args": ["x"], "nargs": "?", "help": "x coordinate"},
            {"args": ["y"], "nargs": "?", "help": "y coordinate"},
        ],
    },
    {
        "action": cmd_double_click,
        "command": "double-click",
        "aliases": ["double_click"],
        "help": "double click coordinates",
        "flags": [
            {"args": ["--duration"], "default": 0.1, "type": float, "help": "delay between taps"},
            {"args": ["x"], "type": float, "help": "x coordinate"},
            {"args": ["y"], "type": float, "help": "y coordinate"},
        ],
    },
    {
        "action": cmd_long_click,
        "command": "long-click",
        "aliases": ["long_click"],
        "help": "long click coordinates or selector",
        "selector": True,
        "flags": [
            {"args": ["--duration"], "default": 0.5, "type": float, "help": "long press duration"},
            {"args": ["--timeout"], "default": 3.0, "type": float, "help": "selector wait timeout"},
            {"args": ["x"], "nargs": "?", "help": "x coordinate"},
            {"args": ["y"], "nargs": "?", "help": "y coordinate"},
        ],
    },
    {
        "action": cmd_swipe,
        "command": "swipe",
        "help": "swipe coordinates or direction",
        "flags": [
            {"args": ["--duration"], "default": 0.5, "type": float, "help": "swipe duration"},
            {"args": ["--steps"], "default": None, "type": int, "help": "number of swipe steps"},
            {"args": ["--scale"], "default": 0.9, "type": float, "help": "direction swipe distance scale"},
            {"args": ["fx"], "help": "direction or from x"},
            {"args": ["fy"], "nargs": "?", "type": float, "help": "from y"},
            {"args": ["tx"], "nargs": "?", "type": float, "help": "to x"},
            {"args": ["ty"], "nargs": "?", "type": float, "help": "to y"},
        ],
    },
    {
        "action": cmd_drag,
        "command": "drag",
        "help": "drag coordinates",
        "flags": [
            {"args": ["--duration"], "default": 0.5, "type": float, "help": "drag duration"},
            {"args": ["sx"], "type": float, "help": "start x"},
            {"args": ["sy"], "type": float, "help": "start y"},
            {"args": ["ex"], "type": float, "help": "end x"},
            {"args": ["ey"], "type": float, "help": "end y"},
        ],
    },
    {
        "action": cmd_exists,
        "command": "exists",
        "help": "check selector exists",
        "selector": True,
        "flags": [{"args": ["--timeout"], "default": 0.0, "type": float, "help": "wait timeout"}],
    },
    {
        "action": cmd_wait,
        "command": "wait",
        "help": "wait selector appear or disappear",
        "selector": True,
        "flags": [
            {"args": ["--timeout"], "default": 3.0, "type": float, "help": "wait timeout"},
            {"args": ["--gone"], "action": "store_true", "help": "wait until gone"},
        ],
    },
    {
        "action": cmd_scroll,
        "command": "scroll",
        "help": "scroll selector",
        "selector": True,
        "flags": [
            {"args": ["--direction"], "choices": ["vert", "horiz"], "default": "vert", "help": "scroll axis"},
            {"args": ["--action"], "choices": ["forward", "backward", "toEnd", "toBeginning"], "default": "forward", "help": "scroll action"},
            {"args": ["--max-swipes"], "default": None, "type": int, "help": "max swipes"},
            {"args": ["--to-text"], "default": None, "help": "scroll until text is visible"},
        ],
    },
]


_HELP_CATEGORIES = [
    ("server commands", [
        "server",
        "start-server",
        "kill-server",
        "server-status",
    ]),
    ("device commands", [
        "device-info",
        "window-size",
        "screenshot",
        "dump-hierarchy",
        "app-current",
        "shell",
    ]),
    ("app commands", [
        "app-start",
        "app-list",
        "app-stop",
        "app-install",
        "app-uninstall",
        "app-clear",
    ]),
    ("input commands", [
        "press",
        "send-keys",
        "clear-text",
        "click",
        "double-click",
        "long-click",
        "swipe",
        "drag",
    ]),
    ("selector commands", [
        "exists",
        "wait",
        "scroll",
    ]),
    ("system ui commands", [
        "open-notification",
        "open-quick-settings",
        "open-url",
    ]),
]


def _command_lookup() -> Dict[str, Dict[str, Any]]:
    return {command["command"]: command for command in _commands}


def _command_display(command: Dict[str, Any]) -> str:
    aliases = command.get("aliases") or []
    if aliases:
        return "%s (%s)" % (command["command"], ", ".join(aliases))
    return command["command"]


def _print_main_help():
    commands = _command_lookup()
    print("usage: u2cli [global options] <command> [command options]")
    print("")
    print("global options:")
    print("  -h, --help                 show this help message and exit")
    print("  -d, --debug                show debug logs")
    print("  -s SERIAL, --serial SERIAL target device serial")
    print("")
    print("Use 'u2cli <command> --help' for command-specific options.")
    for title, command_names in _HELP_CATEGORIES:
        print("")
        print("%s:" % title)
        for command_name in command_names:
            command = commands[command_name]
            print("  %-44s %s" % (_command_display(command), command.get("help", "")))


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        _print_main_help()
        sys.exit(0)

    parser = U2CliArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-d", "--debug", action="store_true", help="show log")
    parser.add_argument("-s", "--serial", type=str, help="device serial number")

    subparser = parser.add_subparsers(dest="subparser", parser_class=U2CliArgumentParser)
    actions = {}
    for c in _commands:
        cmd_name = c["command"]
        actions[cmd_name] = c["action"]
        for alias in c.get("aliases", []):
            actions[alias] = c["action"]
        sp = subparser.add_parser(cmd_name, help=c.get("help"), aliases=c.get("aliases", []),
                      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        _add_server_flags(sp)
        if not c.get("server"):
            _add_device_flags(sp)
        _add_command_flags(sp, c)
        if c.get("selector"):
            _add_selector_flags(sp)

    args = parser.parse_args(argv)
    enable_pretty_logging()
    if args.debug:
        logger.debug("args: %s", args)

    if not args.subparser:
        _output_error_message("command is required", "ArgumentError")
        sys.exit(2)

    try:
        actions[args.subparser](args)
    except U2CliError as e:
        _output_error(e)
        sys.exit(1)
    except Exception as e:
        if args.debug:
            logger.exception("u2cli command failed")
        _output_error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
