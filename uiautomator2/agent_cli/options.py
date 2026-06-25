# coding: utf-8

from __future__ import absolute_import, print_function

import functools
import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

import click

from uiautomator2.agent_cli.click_ext import ChildSelectorOption
from uiautomator2.agent_cli.client import U2CliError
from uiautomator2.agent_cli.output import _output_error
from uiautomator2.core import check_port

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Port validation
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Selector constants
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Selector logic
# ---------------------------------------------------------------------------

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

def _selector_chain(args) -> Tuple[Dict[str, Any], list]:
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
        kwargs["is_flag"] = True
    return kwargs

# ---------------------------------------------------------------------------
# Swipe direction helpers
# ---------------------------------------------------------------------------

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

def _optional_float(value):
    return None if value is None else float(value)

# ===========================================================================
# Shared option decorators
def selector_options(f: F) -> F:
    """Add all selector flags (--text, --resource-id, ...) + --child flag."""
    for option_name, _ in _SELECTOR_OPTIONS:
        opt_kwargs = _selector_option_kwargs(option_name)
        f = click.option(option_name, **opt_kwargs)(f)
    for option_name, _ in _SELECTOR_OPTIONS:
        child_name = "--child-" + option_name[2:]
        opt_kwargs = _selector_option_kwargs(option_name)
        f = click.option(child_name, **opt_kwargs)(f)
    f = click.option("--child", cls=ChildSelectorOption, multiple=True,
                     type=click.UNPROCESSED, metavar="KEY=VALUE [KEY=VALUE ...]",
                     help="append a child selector level, e.g. --child text=OK resourceId=pkg:id/ok")(f)
    return f

def global_options(f: F) -> F:
    """Inject shared options from group ctx.obj, skipping params the function doesn't accept."""
    sig = inspect.signature(f)
    params = sig.parameters

    @click.pass_context
    @functools.wraps(f)
    def wrapper(ctx: click.Context, **kwargs: Any) -> Any:
        root_ctx = ctx.find_root()
        if root_ctx.obj is not None:
            obj = root_ctx.obj
            for key in ("debug", "serial", "server_host", "server_port", "device_port"):
                if key in params:
                    kwargs.setdefault(key, obj.get(key))
        return f(**kwargs)
    return wrapper  # type: ignore[return-value]

def handle_errors(f: F) -> F:
    """Catch exceptions and format them for CLI output."""

    @click.pass_context
    @functools.wraps(f)
    def wrapper(ctx: click.Context, **kwargs: Any) -> None:
        try:
            f(**kwargs)
        except U2CliError as e:
            _output_error(e)
            raise click.exceptions.Exit(1)
        except Exception as e:
            root = ctx.find_root()
            if root.obj is not None and root.obj.get("debug", False):
                logger.exception("u2cli command failed")
            _output_error(e)
            raise click.exceptions.Exit(1)
    return wrapper  # type: ignore[return-value]
