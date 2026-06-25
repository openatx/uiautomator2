# coding: utf-8

from __future__ import absolute_import, print_function

import logging
import pathlib
import sys
from typing import Any, Dict, Optional

import click
from click.parser import normalize_opt
from PIL import Image

from uiautomator2 import enable_pretty_logging
from uiautomator2.agent_cli.client import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT, U2CliClient, U2CliError, \
    ensure_server
from uiautomator2.agent_cli.server import run_server
from uiautomator2.core import DEFAULT_SERVER_PORT as DEFAULT_DEVICE_PORT
from uiautomator2.core import check_port

logger = logging.getLogger(__name__)


def _valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise click.BadParameter("port must be an integer, got %r" % value)
    try:
        check_port(port)
    except ValueError as e:
        raise click.BadParameter(str(e))
    return port


class PortParamType(click.ParamType):
    name = "PORT"

    def convert(self, value, param, ctx):
        try:
            return _valid_port(value)
        except click.BadParameter as e:
            self.fail(e.message, param, ctx)


PORT = PortParamType()


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
        try:
            value = int(value)
        except ValueError:
            raise U2CliError("invalid integer selector value for %s: %s" % (key, value))
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
    payload: Dict[str, Any] = {"selector": selector}
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
    kwargs: Dict[str, Any] = {"default": None}
    if option in ("--index", "--instance"):
        kwargs["type"] = int
    if option in ("--checkable", "--checked", "--clickable", "--scrollable", "--enabled", "--focused", "--selected"):
        kwargs["action"] = "store_true"
    return kwargs


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
    saved_to = result.get("filename") or abs_filename if isinstance(result, dict) else abs_filename
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
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else {}
    if isinstance(result, dict) and result.get("exit_code") is not None:
        extra["exit_code"] = result.get("exit_code")
    _output_result(output, u2_code="d.shell(%r, timeout=%s)" % (command, args.timeout), extra=extra or None)


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


def _command_display(command: click.Command) -> str:
    aliases = getattr(command, "aliases", ())
    if aliases:
        return "%s (%s)" % (command.name, ", ".join(aliases))
    return command.name or ""


def _format_click_metavar(name: str) -> str:
    return name.replace("-", "_").upper()


def _option_help_label(param: click.Option) -> str:
    option_parts = []
    metavar = param.metavar or _format_click_metavar(param.name or "")
    for opt in list(param.opts) + list(param.secondary_opts):
        if param.is_bool_flag:
            option_parts.append(opt)
        else:
            option_parts.append("%s %s" % (opt, metavar))
    return ", ".join(option_parts)


def _argument_help_label(param: click.Argument) -> str:
    name = param.human_readable_name.upper()
    if param.nargs == -1:
        return "%s [%s ...]" % (name, name)
    if not param.required:
        return "[%s]" % name
    return name


class U2CliCommand(click.Command):
    def format_options(self, ctx, formatter):
        for section in ["server options", "device options", "command options", "selector options", "child selector options"]:
            rows = []
            for param in self.params:
                if getattr(param, "help_section", None) != section or getattr(param, "hidden", False):
                    continue
                if isinstance(param, click.Option):
                    rows.append((_option_help_label(param), param.help or ""))
                elif isinstance(param, click.Argument):
                    rows.append((_argument_help_label(param), getattr(param, "help", "") or ""))
            if rows:
                with formatter.section(section):
                    formatter.write_dl(rows)


class U2CliGroup(click.Group):
    def format_commands(self, ctx, formatter):
        return


class CommandArgs(object):
    def __init__(self, params: Dict[str, Any]):
        self.__dict__.update(params)


class ChildSelectorOption(click.Option):
    def add_to_parser(self, parser, ctx):
        super(ChildSelectorOption, self).add_to_parser(parser, ctx)
        for option in self.opts:
            parser_option = parser._long_opt.get(normalize_opt(option, ctx))
            if parser_option is None:
                continue
            process = parser_option.process

            def process_child(value, state, process=process):
                values = [value]
                while state.rargs and not _is_option_token(state.rargs[0], parser):
                    values.append(state.rargs.pop(0))
                process(tuple(values), state)

            parser_option.process = process_child


def _is_option_token(token: str, parser) -> bool:
    return len(token) > 1 and token[:1] in parser._opt_prefixes


def _collect_click_params(ctx: click.Context, params: Dict[str, Any]) -> CommandArgs:
    all_params = {}
    if ctx.parent is not None:
        all_params.update(ctx.parent.params)
    all_params.update(params)
    return CommandArgs(all_params)


def _run_command_action(action, args: CommandArgs):
    try:
        action(args)
    except U2CliError as e:
        _output_error(e)
        raise click.exceptions.Exit(1)
    except Exception as e:
        if getattr(args, "debug", False):
            logger.exception("u2cli command failed")
        _output_error(e)
        raise click.exceptions.Exit(1)


def _make_option(args, kwargs: Dict[str, Any], section: str) -> click.Option:
    kwargs = kwargs.copy()
    action = kwargs.pop("action", None)
    hidden = kwargs.pop("hidden", False)
    help_text = kwargs.pop("help", None)
    default = kwargs.pop("default", None)
    param_type = kwargs.pop("type", None)
    choices = kwargs.pop("choices", None)
    metavar = kwargs.pop("metavar", None)
    kwargs.pop("nargs", None)

    option_kwargs = {"help": help_text, "hidden": hidden}
    if action == "store_true":
        option_kwargs.update({"is_flag": True, "default": bool(default)})
    else:
        option_kwargs["default"] = default
        option_kwargs["metavar"] = metavar or _format_click_metavar(args[-1].lstrip("-").replace("-", "_"))
        if choices:
            option_kwargs["type"] = click.Choice(choices)
        elif param_type is not None:
            option_kwargs["type"] = param_type
    option = click.Option(args, **option_kwargs)
    setattr(option, "help_section", section)
    return option


def _make_argument(name: str, kwargs: Dict[str, Any]) -> click.Argument:
    kwargs = kwargs.copy()
    help_text = kwargs.pop("help", "")
    default = kwargs.pop("default", None)
    param_type = kwargs.pop("type", None)
    nargs = kwargs.pop("nargs", None)
    required = True
    click_nargs = 1
    if nargs == "?":
        required = False
    elif nargs == "+":
        click_nargs = -1
    argument_kwargs = {"required": required, "nargs": click_nargs}
    if default is not None:
        argument_kwargs["default"] = default
    if param_type is not None:
        argument_kwargs["type"] = param_type
    argument = click.Argument([name], **argument_kwargs)
    setattr(argument, "help", help_text)
    setattr(argument, "help_section", "command options")
    return argument


def _click_selector_option_kwargs(option: str) -> Dict[str, Any]:
    kwargs = _selector_option_kwargs(option)
    if option in ("--index", "--instance"):
        kwargs["type"] = int
    return kwargs


def _click_server_flags() -> list:
    return [
        click.Option(["--server-host"], default=DEFAULT_SERVER_HOST, metavar="SERVER_HOST", help="u2cli server listen host"),
        click.Option(["--server-port"], type=PORT, default=DEFAULT_SERVER_PORT, metavar="PORT", help="u2cli server listen port"),
    ]


def _click_device_flags() -> list:
    return [
        click.Option(["-p", "--port"], type=PORT, default=DEFAULT_DEVICE_PORT, metavar="PORT",
                     help="uiautomator2 server port on device (1-65535)"),
    ]


def _click_selector_flags() -> list:
    params = []
    for option, _ in _SELECTOR_OPTIONS:
        params.append(_make_option([option], _click_selector_option_kwargs(option), "selector options"))
    for option, _ in _SELECTOR_OPTIONS:
        params.append(_make_option(["--child-" + option[2:]], _click_selector_option_kwargs(option), "child selector options"))
    child = ChildSelectorOption(["--child"], multiple=True, type=click.UNPROCESSED,
                                metavar="KEY=VALUE [KEY=VALUE ...]",
                                help="append a child selector level, e.g. --child text=OK resourceId=pkg:id/ok")
    setattr(child, "help_section", "child selector options")
    params.append(child)
    return params


def _assign_help_section(params: list, section: str) -> list:
    for param in params:
        setattr(param, "help_section", section)
    return params


def _command_callback(action):
    def callback(**params):
        _run_command_action(action, _collect_click_params(click.get_current_context(), params))
    return callback


def _command_params(params: Optional[list] = None, include_device: bool = True, selector: bool = False) -> list:
    result = []
    result.extend(_assign_help_section(_click_server_flags(), "server options"))
    if include_device:
        result.extend(_assign_help_section(_click_device_flags(), "device options"))
    if params:
        result.extend(params)
    if selector:
        result.extend(_click_selector_flags())
    return result


def _click_command(name: str, action, help_text: str, params: Optional[list] = None,
                   aliases: Optional[tuple] = None) -> click.Command:
    aliases = aliases or ()
    command = U2CliCommand(
        name=name,
        help=help_text,
        params=params or [],
        callback=_command_callback(action),
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    setattr(command, "aliases", aliases)
    return command


def _add_click_command(cli: click.Group, name: str, action, help_text: str, params: Optional[list] = None,
                       aliases: Optional[tuple] = None):
    command = _click_command(name, action, help_text, params=params, aliases=aliases)
    cli.add_command(command, name)
    for alias in aliases or ():
        cli.add_command(command, alias)


def _option(args: list, kwargs: Dict[str, Any]) -> click.Option:
    return _make_option(args, kwargs, "command options")


def _argument(name: str, kwargs: Dict[str, Any]) -> click.Argument:
    return _make_argument(name, kwargs)


def _register_server_commands(cli: click.Group):
    _add_click_command(cli, "server", cmd_server, "run u2cli server in foreground", _command_params([
        _option(["--foreground"], {"action": "store_true", "hidden": True}),
    ], include_device=False))
    _add_click_command(cli, "start-server", cmd_start_server, "start u2cli server",
                       _command_params(include_device=False))
    _add_click_command(cli, "kill-server", cmd_kill_server, "stop u2cli server",
                       _command_params(include_device=False))
    _add_click_command(cli, "server-status", cmd_server_status, "show u2cli server status",
                       _command_params(include_device=False))


def _register_device_commands(cli: click.Group):
    _add_click_command(cli, "screenshot", cmd_screenshot, "take device screenshot", _command_params([
        _argument("filename", {"nargs": "?", "default": "screenshot.jpg", "type": str,
                               "help": "output filename, jpg or png"}),
    ]))
    _add_click_command(cli, "dump-hierarchy", cmd_dump_hierarchy, "dump UI hierarchy", _command_params([
        _option(["--compressed"], {"action": "store_true", "help": "use compressed hierarchy"}),
        _option(["--max-depth"], {"default": None, "type": int, "help": "maximum hierarchy depth"}),
        _option(["--output", "-o"], {"default": None, "help": "save output to file"}),
        _option(["--raw"], {"action": "store_true", "help": "output raw XML without simplification"}),
    ]))
    _add_click_command(cli, "app-current", cmd_app_current, "show current foreground app",
                       _command_params(), aliases=("app_current",))
    _add_click_command(cli, "device-info", cmd_device_info, "show device information",
                       _command_params(), aliases=("device_info",))
    _add_click_command(cli, "window-size", cmd_window_size, "show screen window size",
                       _command_params(), aliases=("window_size",))
    _add_click_command(cli, "shell", cmd_shell, "run shell command", _command_params([
        _option(["--timeout"], {"default": 60, "type": int, "help": "command timeout in seconds"}),
        _argument("cmd", {"nargs": "+", "help": "shell command"}),
    ]))


def _register_app_commands(cli: click.Group):
    _add_click_command(cli, "app-start", cmd_app_start, "start application", _command_params([
        _option(["--activity"], {"default": None, "help": "specific activity to launch"}),
        _option(["--wait"], {"action": "store_true", "help": "wait for app to launch"}),
        _option(["--stop"], {"action": "store_true", "help": "stop app before launching"}),
        _argument("package", {"help": "package name"}),
    ]), aliases=("app_start",))
    _add_click_command(cli, "app-list", cmd_app_list, "list installed packages", _command_params([
        _option(["--filter"], {"default": "", "help": "filter string passed to pm list packages"}),
    ]), aliases=("app_list",))
    _add_click_command(cli, "app-stop", cmd_app_stop, "stop application", _command_params([
        _option(["--all"], {"action": "store_true", "help": "stop all third-party apps"}),
        _argument("package", {"nargs": "?", "help": "package name"}),
    ]), aliases=("app_stop",))
    _add_click_command(cli, "app-install", cmd_app_install, "install application", _command_params([
        _argument("apk", {"help": "apk path or url"}),
    ]), aliases=("app_install",))
    _add_click_command(cli, "app-uninstall", cmd_app_uninstall, "uninstall application", _command_params([
        _argument("package", {"help": "package name"}),
    ]), aliases=("app_uninstall",))
    _add_click_command(cli, "app-clear", cmd_app_clear, "clear application data", _command_params([
        _argument("package", {"help": "package name"}),
    ]), aliases=("app_clear",))


def _register_system_ui_commands(cli: click.Group):
    _add_click_command(cli, "open-notification", cmd_open_notification, "open notification shade",
                       _command_params(), aliases=("open_notification",))
    _add_click_command(cli, "open-quick-settings", cmd_open_quick_settings, "open quick settings",
                       _command_params(), aliases=("open_quick_settings",))
    _add_click_command(cli, "open-url", cmd_open_url, "open url", _command_params([
        _argument("url", {"help": "url to open"}),
    ]), aliases=("open_url",))


def _register_input_commands(cli: click.Group):
    _add_click_command(cli, "press", cmd_press, "press key", _command_params([
        _argument("key", {"help": "key name or key code"}),
    ]))
    _add_click_command(cli, "send-keys", cmd_send_keys, "type text into focused input", _command_params([
        _option(["--no-clear"], {"action": "store_true", "help": "do not clear before typing"}),
        _argument("text", {"help": "text to type"}),
    ]), aliases=("send_keys",))
    _add_click_command(cli, "clear-text", cmd_clear_text, "clear focused input text",
                       _command_params(), aliases=("clear_text",))
    _add_click_command(cli, "click", cmd_click, "click coordinates or selector", _command_params([
        _option(["--timeout"], {"default": 3.0, "type": float, "help": "selector wait timeout"}),
        _argument("x", {"nargs": "?", "help": "x coordinate"}),
        _argument("y", {"nargs": "?", "help": "y coordinate"}),
    ], selector=True))
    _add_click_command(cli, "double-click", cmd_double_click, "double click coordinates", _command_params([
        _option(["--duration"], {"default": 0.1, "type": float, "help": "delay between taps"}),
        _argument("x", {"type": float, "help": "x coordinate"}),
        _argument("y", {"type": float, "help": "y coordinate"}),
    ]), aliases=("double_click",))
    _add_click_command(cli, "long-click", cmd_long_click, "long click coordinates or selector", _command_params([
        _option(["--duration"], {"default": 0.5, "type": float, "help": "long press duration"}),
        _option(["--timeout"], {"default": 3.0, "type": float, "help": "selector wait timeout"}),
        _argument("x", {"nargs": "?", "help": "x coordinate"}),
        _argument("y", {"nargs": "?", "help": "y coordinate"}),
    ], selector=True), aliases=("long_click",))
    _add_click_command(cli, "swipe", cmd_swipe, "swipe coordinates or direction", _command_params([
        _option(["--duration"], {"default": 0.5, "type": float, "help": "swipe duration"}),
        _option(["--steps"], {"default": None, "type": int, "help": "number of swipe steps"}),
        _option(["--scale"], {"default": 0.9, "type": float, "help": "direction swipe distance scale"}),
        _argument("fx", {"help": "direction or from x"}),
        _argument("fy", {"nargs": "?", "type": float, "help": "from y"}),
        _argument("tx", {"nargs": "?", "type": float, "help": "to x"}),
        _argument("ty", {"nargs": "?", "type": float, "help": "to y"}),
    ]))
    _add_click_command(cli, "drag", cmd_drag, "drag coordinates", _command_params([
        _option(["--duration"], {"default": 0.5, "type": float, "help": "drag duration"}),
        _argument("sx", {"type": float, "help": "start x"}),
        _argument("sy", {"type": float, "help": "start y"}),
        _argument("ex", {"type": float, "help": "end x"}),
        _argument("ey", {"type": float, "help": "end y"}),
    ]))


def _register_selector_commands(cli: click.Group):
    _add_click_command(cli, "exists", cmd_exists, "check selector exists", _command_params([
        _option(["--timeout"], {"default": 0.0, "type": float, "help": "wait timeout"}),
    ], selector=True))
    _add_click_command(cli, "wait", cmd_wait, "wait selector appear or disappear", _command_params([
        _option(["--timeout"], {"default": 3.0, "type": float, "help": "wait timeout"}),
        _option(["--gone"], {"action": "store_true", "help": "wait until gone"}),
    ], selector=True))
    _add_click_command(cli, "scroll", cmd_scroll, "scroll selector", _command_params([
        _option(["--direction"], {"choices": ["vert", "horiz"], "default": "vert", "help": "scroll axis"}),
        _option(["--action"], {"choices": ["forward", "backward", "toEnd", "toBeginning"], "default": "forward",
                                "help": "scroll action"}),
        _option(["--max-swipes"], {"default": None, "type": int, "help": "max swipes"}),
        _option(["--to-text"], {"default": None, "help": "scroll until text is visible"}),
    ], selector=True))


def _build_click_cli() -> click.Group:
    def callback(debug, serial):
        enable_pretty_logging()
        if debug:
            logger.debug("debug mode enabled")

    cli = U2CliGroup(
        name="u2cli",
        callback=callback,
        params=[
            click.Option(["-d", "--debug"], is_flag=True, help="show log"),
            click.Option(["-s", "--serial"], type=str, metavar="SERIAL", help="device serial number"),
        ],
        invoke_without_command=False,
        no_args_is_help=False,
        context_settings={"help_option_names": ["-h", "--help"]},
    )

    _register_server_commands(cli)
    _register_device_commands(cli)
    _register_app_commands(cli)
    _register_system_ui_commands(cli)
    _register_input_commands(cli)
    _register_selector_commands(cli)

    return cli


def _print_main_help():
    commands = _build_click_cli().commands
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
            print("  %-44s %s" % (_command_display(command), command.help or ""))


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        _print_main_help()
        sys.exit(0)
    if not argv:
        _output_error_message("command is required", "ArgumentError")
        sys.exit(2)

    try:
        exit_code = _build_click_cli().main(args=list(argv), prog_name="u2cli", standalone_mode=False)
        if exit_code is not None:
            sys.exit(exit_code)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
    except click.ClickException as e:
        _output_error_message(e.format_message(), e.__class__.__name__)
        sys.exit(e.exit_code)


if __name__ == "__main__":
    main()
