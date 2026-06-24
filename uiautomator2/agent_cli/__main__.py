# coding: utf-8

from __future__ import absolute_import, print_function

import argparse
import json
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


class JsonArgumentParser(argparse.ArgumentParser):
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


def _print_json(data: Dict[str, Any]):
    print(json.dumps(data, default=str, ensure_ascii=False, indent=2))


def _output_result(result: Any = None, u2_code: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
    data = {}
    if u2_code:
        data["u2_code"] = u2_code
    if extra:
        data.update(extra)
    if result is not None:
        data["result"] = result
    _print_json(data)


def _output_message(message: str, ok: bool = True, extra: Optional[Dict[str, Any]] = None):
    data = {"ok": ok, "message": message}
    if extra:
        data.update(extra)
    _print_json(data)


def _output_error(exc: BaseException):
    _output_error_message(str(exc), exc.__class__.__name__)


def _output_error_message(message: str, error_type: str):
    print(json.dumps({"error": message, "type": error_type}, ensure_ascii=False, indent=2), file=sys.stderr)


def _image_resolution(filename: str) -> Optional[str]:
    try:
        with Image.open(filename) as image:
            width, height = image.size
    except OSError:
        return None
    return "%sx%s" % (width, height)


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
        _print_json(status)
        return
    status = client.status()
    status["running"] = True
    _print_json(status)


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
    if not resolution:
        resolution = _image_resolution(saved_to)
    extra = {"saved_to": saved_to}
    if resolution:
        extra["resolution"] = resolution
    _output_result(
        u2_code="d.screenshot(%r)" % args.filename,
        extra=extra,
    )


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
]


def main(argv=None):
    # -p must come after the subcommand: `u2cli screenshot -p 9009 screenshot.jpg`
    device_shared = JsonArgumentParser(add_help=False)
    device_shared.add_argument("-p", "--port", type=_valid_port, default=DEFAULT_DEVICE_PORT,
                               help="uiautomator2 server port on device (1-65535)")

    server_shared = JsonArgumentParser(add_help=False)
    server_shared.add_argument("--server-host", default=DEFAULT_SERVER_HOST,
                               help="u2cli server listen host")
    server_shared.add_argument("--server-port", type=_valid_port, default=DEFAULT_SERVER_PORT,
                               help="u2cli server listen port")

    parser = JsonArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-d", "--debug", action="store_true", help="show log")
    parser.add_argument("-s", "--serial", type=str, help="device serial number")

    subparser = parser.add_subparsers(dest="subparser", parser_class=JsonArgumentParser)
    actions = {}
    for c in _commands:
        cmd_name = c["command"]
        actions[cmd_name] = c["action"]
        parents = [server_shared]
        if not c.get("server"):
            parents.append(device_shared)
        sp = subparser.add_parser(cmd_name, help=c.get("help"), parents=parents,
                      formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        for f in c.get("flags", []):
            kwargs = f.copy()
            args = kwargs.pop("args")
            sp.add_argument(*args, **kwargs)

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


if __name__ == "__main__":
    main()
