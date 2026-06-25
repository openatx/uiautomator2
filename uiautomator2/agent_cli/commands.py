# coding: utf-8

from __future__ import absolute_import, print_function

import logging
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

import click

from uiautomator2 import enable_pretty_logging

from uiautomator2.agent_cli.click_ext import CategorizedGroup
from uiautomator2.agent_cli.client import U2CliClient, U2CliError, ensure_server
from uiautomator2.agent_cli.options import (
    _normalize_swipe_direction,
    _optional_float,
    _parse_swipe_fx,
    _require_selector,
    _selector_chain,
    _selector_chain_code,
    _selector_chain_payload,
    global_options,
    handle_errors,
    selector_options,
)
from uiautomator2.agent_cli.output import (
    _absolute_filename,
    _image_resolution,
    _output_message,
    _output_result,
    _output_text,
    _parse_key,
)
from uiautomator2.agent_cli.server import run_server

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------
@click.group(
    name="u2cli",
    cls=CategorizedGroup,
    invoke_without_command=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("-d", "--debug", is_flag=True, help="show log")
@click.option("-s", "--serial", type=str, metavar="SERIAL", help="device serial number")
@click.option("--server-host", default="127.0.0.1", metavar="HOST", help="u2cli server listen host")
@click.option("--server-port", type=int, default=17913, metavar="PORT", help="u2cli server listen port")
@click.option("--device-port", type=int, default=9008, metavar="PORT", help="uiautomator2 server port on device")
@click.pass_context
def cli(
    ctx: click.Context,
    debug: bool,
    serial: Optional[str],
    server_host: str,
    server_port: int,
    device_port: int,
) -> None:
    """u2cli — command line interface for uiautomator2."""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    ctx.obj["serial"] = serial
    ctx.obj["server_host"] = server_host
    ctx.obj["server_port"] = server_port
    ctx.obj["device_port"] = device_port
    enable_pretty_logging()
    if debug:
        logger.debug("debug mode enabled")
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_global(key: str):
    return click.get_current_context().find_root().obj[key]

def _request_device_method(
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    g = _get_global
    client, _ = ensure_server(g("server_host"), g("server_port"))
    payload: Dict[str, Any] = {"serial": g("serial"), "port": g("device_port")}
    if params:
        payload.update(params)
    return client.request(method, payload)

# ---------------------------------------------------------------------------
# Server commands
# ---------------------------------------------------------------------------

@cli.command(
    name="server",
    help="run u2cli server in foreground",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--foreground", is_flag=True, hidden=True)
@global_options
@handle_errors
def cmd_server(
    foreground: bool,
) -> None:
    """Run u2cli server in foreground."""
    run_server(_get_global("server_host"), _get_global("server_port"))

@cli.command(
    name="start-server",
    help="start u2cli server",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_start_server(
) -> None:
    """Start u2cli server."""
    _, started = ensure_server(_get_global("server_host"), _get_global("server_port"))
    if started:
        message = "u2cli server started"
    else:
        message = "u2cli server is already running"
    _output_message(message, extra={"host": _get_global("server_host"), "port": _get_global("server_port")})

@cli.command(
    name="kill-server",
    help="stop u2cli server",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_kill_server(
) -> None:
    """Stop u2cli server."""
    client = U2CliClient(_get_global("server_host"), _get_global("server_port"))
    if not client.is_running():
        _output_message("u2cli server is not running")
        return
    client.request("server.stop", timeout=2.0)
    _output_message("u2cli server stopped")

@cli.command(
    name="server-status",
    help="show u2cli server status",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_server_status(
) -> None:
    """Show u2cli server status."""
    client = U2CliClient(_get_global("server_host"), _get_global("server_port"))
    if not client.is_running():
        status = {"running": False, "host": _get_global("server_host"), "port": _get_global("server_port")}
        _output_result(status)
        return
    status = client.status()
    status["running"] = True
    _output_result(status)
# ---------------------------------------------------------------------------
# Device commands
# ---------------------------------------------------------------------------

@cli.command(
    name="screenshot",
    help="take device screenshot",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("filename", required=False, default="screenshot.jpg", metavar="FILENAME")
@global_options
@handle_errors
def cmd_screenshot(
    filename: str,
) -> None:
    """Take device screenshot."""
    client, _ = ensure_server(_get_global("server_host"), _get_global("server_port"))
    abs_filename = _absolute_filename(filename)
    result = client.request("screenshot", {
        "serial": _get_global("serial"),
        "port": _get_global("device_port"),
        "filename": abs_filename,
    })
    saved_to = result.get("filename") or abs_filename if isinstance(result, dict) else abs_filename
    resolution = result.get("resolution") if isinstance(result, dict) else None
    device_serial = result.get("device_serial") if isinstance(result, dict) else _get_global("serial")
    if not resolution:
        resolution = _image_resolution(saved_to)
    extra: Dict[str, Any] = {"saved_to": saved_to}
    if device_serial:
        extra["device_serial"] = device_serial
    if resolution:
        extra["resolution"] = resolution
    _output_result(
        u2_code="d.screenshot(%r)" % filename,
        extra=extra,
    )

@cli.command(
    name="dump-hierarchy",
    help="dump UI hierarchy",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--compressed", is_flag=True, help="use compressed hierarchy")
@click.option("--max-depth", default=None, type=int, help="maximum hierarchy depth")
@click.option("--output", "-o", default=None, help="save output to file")
@click.option("--raw", is_flag=True, help="output raw XML without simplification")
@global_options
@handle_errors
def cmd_dump_hierarchy(
    compressed: bool,
    max_depth: Optional[int],
    output: Optional[str],
    raw: bool,
) -> None:
    """Dump UI hierarchy."""
    client, _ = ensure_server(_get_global("server_host"), _get_global("server_port"))
    out_file = _absolute_filename(output) if output else None
    result = client.request("dump_hierarchy", {
        "serial": _get_global("serial"),
        "port": _get_global("device_port"),
        "compressed": compressed,
        "max_depth": max_depth,
        "raw": raw,
        "output": out_file,
    })
    _parts = []
    if compressed:
        _parts.append("compressed=True")
    if max_depth is not None:
        _parts.append("max_depth=%s" % max_depth)
    u2_code = "d.dump_hierarchy(%s)" % ", ".join(_parts)
    device_serial = result.get("device_serial") if isinstance(result, dict) else _get_global("serial")
    if out_file:
        saved_to = result.get("filename") if isinstance(result, dict) else out_file
        extra: Dict[str, Any] = {"saved_to": saved_to}
        if device_serial:
            extra["device_serial"] = device_serial
        _output_result(u2_code=u2_code, extra=extra)
        return

    content = result.get("content") if isinstance(result, dict) else result
    _output_result(u2_code=u2_code, extra={"device_serial": device_serial} if device_serial else None)
    if content:
        _output_text(content)

@cli.command(
    name="app-current",
    help="show current foreground app",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_app_current(
) -> None:
    """Show current foreground app."""
    result = _request_device_method("app_current")
    _output_result(result, u2_code="d.app_current()")

@cli.command(
    name="device-info",
    help="show device information",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_device_info(
) -> None:
    """Show device information."""
    result = _request_device_method("device_info")
    _output_result(result, u2_code="d.device_info")

@cli.command(
    name="window-size",
    help="show screen window size",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_window_size(
) -> None:
    """Show screen window size."""
    result = _request_device_method("window_size")
    _output_result(result, u2_code="d.window_size()")

@cli.command(
    name="shell",
    help="run shell command",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--timeout", default=60, type=int, help="command timeout in seconds")
@click.argument("cmd", nargs=-1, required=True, metavar="CMD")
@global_options
@handle_errors
def cmd_shell(
    timeout: int,
    cmd: Tuple[str, ...],
) -> None:
    """Run shell command on device."""
    command = " ".join(cmd)
    result = _request_device_method("shell",
                                    {"command": command, "timeout": timeout})
    output = result.get("output") if isinstance(result, dict) else result
    extra: Dict[str, Any] = {}
    device_serial = result.get("device_serial") if isinstance(result, dict) else None
    if device_serial:
        extra["device_serial"] = device_serial
    if isinstance(result, dict) and result.get("exit_code") is not None:
        extra["exit_code"] = result.get("exit_code")
    _output_result(output, u2_code="d.shell(%r, timeout=%s)" % (command, timeout),
                   extra=extra or None)
# ---------------------------------------------------------------------------
# App commands
# ---------------------------------------------------------------------------

@cli.command(
    name="app-start",
    help="start application",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--activity", default=None, help="specific activity to launch")
@click.option("--wait", is_flag=True, help="wait for app to launch")
@click.option("--stop", is_flag=True, help="stop app before launching")
@click.argument("package", metavar="PACKAGE")
@global_options
@handle_errors
def cmd_app_start(
    activity: Optional[str],
    wait: bool,
    stop: bool,
    package: str,
) -> None:
    """Start application."""
    params = {
        "package": package,
        "activity": activity,
        "wait": wait,
        "stop": stop,
    }
    result = _request_device_method("app_start", params)
    parts = [repr(package)]
    if activity:
        parts.append("activity=%r" % activity)
    if wait:
        parts.append("wait=True")
    if stop:
        parts.append("stop=True")
    _output_result(result, u2_code="d.app_start(%s)" % ", ".join(parts))
    
@cli.command(
    name="app-list",
    help="list installed packages",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--filter", "filter_", default="", help="filter string passed to pm list packages")
@global_options
@handle_errors
def cmd_app_list(
    filter_: str,
) -> None:
    """List installed packages."""
    result = _request_device_method("app_list",
                                    {"filter": filter_})
    packages = result.get("packages") if isinstance(result, dict) else result
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    if filter_:
        u2_code = "d.app_list(%r)" % filter_
    else:
        u2_code = "d.app_list()"
    _output_result(packages, u2_code=u2_code, extra=extra)

@cli.command(
    name="app-stop",
    help="stop application",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--all", "all_", is_flag=True, help="stop all third-party apps")
@click.argument("package", required=False, default=None, metavar="PACKAGE")
@global_options
@handle_errors
def cmd_app_stop(
    all_: bool,
    package: Optional[str],
) -> None:
    """Stop application."""
    if not all_ and not package:
        raise U2CliError("package is required unless --all is used")
    result = _request_device_method("app_stop",
                                    {"package": package, "all": all_})
    if all_:
        u2_code = "d.app_stop_all()"
    else:
        u2_code = "d.app_stop(%r)" % package
    _output_result(result, u2_code=u2_code)

@cli.command(
    name="app-install",
    help="install application",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("apk", metavar="APK")
@global_options
@handle_errors
def cmd_app_install(
    apk: str,
) -> None:
    """Install application."""
    result = _request_device_method("app_install",
                                    {"apk": apk})
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    install_result = result.get("result") if isinstance(result, dict) else result
    _output_result(install_result, u2_code="d.app_install(%r)" % apk, extra=extra)

@cli.command(
    name="app-uninstall",
    help="uninstall application",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("package", metavar="PACKAGE")
@global_options
@handle_errors
def cmd_app_uninstall(
    package: str,
) -> None:
    """Uninstall application."""
    result = _request_device_method("app_uninstall",
                                    {"package": package})
    extra = {"device_serial": result.get("device_serial")} if isinstance(result, dict) else None
    uninstall_result = result.get("result") if isinstance(result, dict) else result
    _output_result(uninstall_result, u2_code="d.app_uninstall(%r)" % package, extra=extra)

@cli.command(
    name="app-clear",
    help="clear application data",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("package", metavar="PACKAGE")
@global_options
@handle_errors
def cmd_app_clear(
    package: str,
) -> None:
    """Clear application data."""
    result = _request_device_method("app_clear",
                                    {"package": package})
    _output_result(result, u2_code="d.app_clear(%r)" % package)
# ---------------------------------------------------------------------------
# System UI commands
# ---------------------------------------------------------------------------

@cli.command(
    name="open-notification",
    help="open notification shade",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_open_notification(
) -> None:
    """Open notification shade."""
    result = _request_device_method("open_notification")
    _output_result(result, u2_code="d.open_notification()")

@cli.command(
    name="open-quick-settings",
    help="open quick settings",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_open_quick_settings(
) -> None:
    """Open quick settings."""
    result = _request_device_method("open_quick_settings")
    _output_result(result, u2_code="d.open_quick_settings()")

@cli.command(
    name="open-url",
    help="open url",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("url", metavar="URL")
@global_options
@handle_errors
def cmd_open_url(
    url: str,
) -> None:
    """Open URL."""
    result = _request_device_method("open_url",
                                    {"url": url})
    _output_result(result, u2_code="d.open_url(%r)" % url)
# ---------------------------------------------------------------------------
# Input commands
# ---------------------------------------------------------------------------

@cli.command(
    name="press",
    help="press key",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument("key", metavar="KEY")
@global_options
@handle_errors
def cmd_press(
    key: str,
) -> None:
    """Press key."""
    parsed = _parse_key(key)
    result = _request_device_method("press",
                                    {"key": parsed})
    if isinstance(parsed, int):
        u2_code = "d.press(%s)" % parsed
    else:
        u2_code = "d.press(%r)" % parsed
    _output_result(result, u2_code=u2_code)

@cli.command(
    name="send-keys",
    help="type text into focused input",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--no-clear", is_flag=True, help="do not clear before typing")
@click.argument("text", metavar="TEXT")
@global_options
@handle_errors
def cmd_send_keys(
    no_clear: bool,
    text: str,
) -> None:
    """Type text into focused input."""
    clear = not no_clear
    result = _request_device_method("send_keys",
                                    {"text": text, "clear": clear})
    _output_result(result, u2_code="d.send_keys(%r, clear=%s)" % (text, clear))

@cli.command(
    name="clear-text",
    help="clear focused input text",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@global_options
@handle_errors
def cmd_clear_text(
) -> None:
    """Clear focused input text."""
    result = _request_device_method("clear_text")
    _output_result(result, u2_code="d.clear_text()")

@cli.command(
    name="click",
    help="click coordinates or selector",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--timeout", default=3.0, type=float, help="selector wait timeout")
@click.argument("x", required=False, default=None, metavar="X")
@click.argument("y", required=False, default=None, metavar="Y")
@selector_options
@global_options
@handle_errors
def cmd_click(
    timeout: float,
    x: Optional[str],
    y: Optional[str],
    **kwargs: Any,
) -> None:
    """Click coordinates or selector."""

    args = SimpleNamespace(**kwargs)
    args.x = x
    args.y = y
    args.server_host = _get_global("server_host")
    args.server_port = _get_global("server_port")
    args.port = _get_global("device_port")
    args.serial = _get_global("serial")
    args.timeout = timeout

    selector, child_selectors = _selector_chain(args)
    fx = _optional_float(x)
    fy = _optional_float(y)
    if selector:
        payload = _selector_chain_payload(selector, child_selectors)
        payload["timeout"] = timeout
        result = _request_device_method("click", payload)
        u2_code = "%s.click(timeout=%s)" % (_selector_chain_code(selector, child_selectors), timeout)
    else:
        if fx is None or fy is None:
            raise U2CliError("x and y are required when no selector option is used")
        result = _request_device_method("click",
                                        {"x": fx, "y": fy})
        u2_code = "d.click(%s, %s)" % (fx, fy)
    _output_result(result, u2_code=u2_code)

@cli.command(
    name="double-click",
    help="double click coordinates",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--duration", default=0.1, type=float, help="delay between taps")
@click.argument("x", type=float, metavar="X")
@click.argument("y", type=float, metavar="Y")
@global_options
@handle_errors
def cmd_double_click(
    duration: float,
    x: float,
    y: float,
) -> None:
    """Double click coordinates."""
    result = _request_device_method("double_click", {
        "x": x,
        "y": y,
        "duration": duration,
    })
    _output_result(result, u2_code="d.double_click(%s, %s, duration=%s)" % (x, y, duration))

@cli.command(
    name="long-click",
    help="long click coordinates or selector",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--duration", default=0.5, type=float, help="long press duration")
@click.option("--timeout", default=3.0, type=float, help="selector wait timeout")
@click.argument("x", required=False, default=None, metavar="X")
@click.argument("y", required=False, default=None, metavar="Y")
@selector_options
@global_options
@handle_errors
def cmd_long_click(
    duration: float,
    timeout: float,
    x: Optional[str],
    y: Optional[str],
    **kwargs: Any,
) -> None:
    """Long click coordinates or selector."""

    args = SimpleNamespace(**kwargs)
    args.x = x
    args.y = y
    args.server_host = _get_global("server_host")
    args.server_port = _get_global("server_port")
    args.port = _get_global("device_port")
    args.serial = _get_global("serial")
    args.duration = duration
    args.timeout = timeout

    selector, child_selectors = _selector_chain(args)
    fx = _optional_float(x)
    fy = _optional_float(y)
    if selector:
        payload = _selector_chain_payload(selector, child_selectors)
        payload.update({
            "duration": duration,
            "timeout": timeout,
        })
        result = _request_device_method("long_click", payload)
        u2_code = "%s.long_click(duration=%s, timeout=%s)" % (
            _selector_chain_code(selector, child_selectors), duration, timeout)
    else:
        if fx is None or fy is None:
            raise U2CliError("x and y are required when no selector option is used")
        result = _request_device_method("long_click",
                                        {"x": fx, "y": fy, "duration": duration})
        u2_code = "d.long_click(%s, %s, duration=%s)" % (fx, fy, duration)
    _output_result(result, u2_code=u2_code)

@cli.command(
    name="swipe",
    help="swipe coordinates or direction",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--duration", default=0.5, type=float, help="swipe duration")
@click.option("--steps", default=None, type=int, help="number of swipe steps")
@click.option("--scale", default=0.9, type=float, help="direction swipe distance scale")
@click.argument("fx", metavar="FX")
@click.argument("fy", required=False, default=None, type=float, metavar="FY")
@click.argument("tx", required=False, default=None, type=float, metavar="TX")
@click.argument("ty", required=False, default=None, type=float, metavar="TY")
@global_options
@handle_errors
def cmd_swipe(
    duration: float,
    steps: Optional[int],
    scale: float,
    fx: str,
    fy: Optional[float],
    tx: Optional[float],
    ty: Optional[float],
) -> None:
    """Swipe coordinates or direction."""
    direction = _normalize_swipe_direction(fx)
    if direction:
        if fy is not None or tx is not None or ty is not None:
            raise U2CliError("coordinate arguments are not allowed when swipe direction is used")
        params: Dict[str, Any] = {"direction": direction, "scale": scale,
                                   "duration": duration, "steps": steps}
        result = _request_device_method("swipe", params)
        if steps is not None:
            u2_code = "d.swipe_ext(%r, scale=%s, steps=%s)" % (direction, scale, steps)
        else:
            u2_code = "d.swipe_ext(%r, scale=%s, duration=%s)" % (direction, scale, duration)
        _output_result(result, u2_code=u2_code)
        return

    if fy is None or tx is None or ty is None:
        raise U2CliError("fx, fy, tx and ty are required when swipe direction is not used")
    if scale != 0.9:
        raise U2CliError("--scale is only supported when swipe direction is used")

    parsed_fx = _parse_swipe_fx(fx)
    params = {"fx": parsed_fx, "fy": fy, "tx": tx, "ty": ty, "duration": duration, "steps": steps}
    result = _request_device_method("swipe", params)
    if steps is not None:
        u2_code = "d.swipe(%s, %s, %s, %s, steps=%s)" % (parsed_fx, fy, tx, ty, steps)
    else:
        u2_code = "d.swipe(%s, %s, %s, %s, duration=%s)" % (parsed_fx, fy, tx, ty, duration)
    _output_result(result, u2_code=u2_code)

@cli.command(
    name="drag",
    help="drag coordinates",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--duration", default=0.5, type=float, help="drag duration")
@click.argument("sx", type=float, metavar="SX")
@click.argument("sy", type=float, metavar="SY")
@click.argument("ex", type=float, metavar="EX")
@click.argument("ey", type=float, metavar="EY")
@global_options
@handle_errors
def cmd_drag(
    duration: float,
    sx: float,
    sy: float,
    ex: float,
    ey: float,
) -> None:
    """Drag coordinates."""
    result = _request_device_method("drag", {
        "sx": sx,
        "sy": sy,
        "ex": ex,
        "ey": ey,
        "duration": duration,
    })
    _output_result(result, u2_code="d.drag(%s, %s, %s, %s, duration=%s)" % (sx, sy, ex, ey, duration))
# ---------------------------------------------------------------------------
# Selector commands
# ---------------------------------------------------------------------------

@cli.command(
    name="exists",
    help="check selector exists",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--timeout", default=0.0, type=float, help="wait timeout")
@selector_options
@global_options
@handle_errors
def cmd_exists(
    timeout: float,
    **kwargs: Any,
) -> None:
    """Check if selector exists."""

    args = SimpleNamespace(**kwargs)
    args.timeout = timeout

    selector, child_selectors = _selector_chain(args)
    _require_selector(selector)
    payload = _selector_chain_payload(selector, child_selectors)
    payload["timeout"] = timeout
    result = _request_device_method("selector_exists", payload)
    if timeout:
        u2_code = "%s.exists(timeout=%s)" % (_selector_chain_code(selector, child_selectors), timeout)
    else:
        u2_code = "%s.exists" % _selector_chain_code(selector, child_selectors)
    device_serial = result.get("device_serial") if isinstance(result, dict) else None
    exists = result.get("result") if isinstance(result, dict) else result
    _output_result(exists, u2_code=u2_code,
                   extra={"device_serial": device_serial} if device_serial else None)

@cli.command(
    name="wait",
    help="wait selector appear or disappear",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--timeout", default=3.0, type=float, help="wait timeout")
@click.option("--gone", is_flag=True, help="wait until gone")
@selector_options
@global_options
@handle_errors
def cmd_wait(
    timeout: float,
    gone: bool,
    **kwargs: Any,
) -> None:
    """Wait for selector to appear or disappear."""

    args = SimpleNamespace(**kwargs)
    args.timeout = timeout
    args.gone = gone

    selector, child_selectors = _selector_chain(args)
    _require_selector(selector)
    payload = _selector_chain_payload(selector, child_selectors)
    payload.update({"timeout": timeout, "gone": gone})
    result = _request_device_method("selector_wait", payload)
    if gone:
        u2_code = "%s.wait_gone(timeout=%s)" % (_selector_chain_code(selector, child_selectors), timeout)
    else:
        u2_code = "%s.wait(timeout=%s)" % (_selector_chain_code(selector, child_selectors), timeout)
    device_serial = result.get("device_serial") if isinstance(result, dict) else None
    wait_result = result.get("result") if isinstance(result, dict) else result
    _output_result(wait_result, u2_code=u2_code,
                   extra={"device_serial": device_serial} if device_serial else None)

@cli.command(
    name="scroll",
    help="scroll selector",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--direction", type=click.Choice(["vert", "horiz"]), default="vert",
              help="scroll axis")
@click.option("--action", type=click.Choice(["forward", "backward", "toEnd", "toBeginning"]),
              default="forward", help="scroll action")
@click.option("--max-swipes", default=None, type=int, help="max swipes")
@click.option("--to-text", default=None, help="scroll until text is visible")
@selector_options
@global_options
@handle_errors
def cmd_scroll(
    direction: str,
    action: str,
    max_swipes: Optional[int],
    to_text: Optional[str],
    **kwargs: Any,
) -> None:
    """Scroll selector."""

    args = SimpleNamespace(**kwargs)
    args.direction = direction
    args.action = action
    args.max_swipes = max_swipes
    args.to_text = to_text

    selector, child_selectors = _selector_chain(args)
    _require_selector(selector)
    payload = _selector_chain_payload(selector, child_selectors)
    payload.update({
        "direction": direction,
        "action": action,
        "max_swipes": max_swipes,
        "to_text": to_text,
    })
    result = _request_device_method("selector_scroll", payload)
    if to_text:
        u2_code = "%s.scroll.%s.to(text=%r)" % (
            _selector_chain_code(selector, child_selectors), direction, to_text)
    elif max_swipes is not None:
        u2_code = "%s.scroll.%s.%s(max_swipes=%s)" % (
            _selector_chain_code(selector, child_selectors), direction, action, max_swipes)
    else:
        u2_code = "%s.scroll.%s.%s()" % (
            _selector_chain_code(selector, child_selectors), direction, action)
    _output_result(result, u2_code=u2_code)
