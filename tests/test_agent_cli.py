# coding: utf-8

import json
import logging
from unittest.mock import Mock, patch

import pytest

from uiautomator2.agent_cli.__main__ import main
from uiautomator2.agent_cli.server import DeviceRegistry, U2CliRequestHandler
from uiautomator2.core import DEFAULT_SERVER_PORT


class FakeImage(object):
    size = (1080, 2400)

    def __init__(self):
        self.saved_to = None

    def save(self, filename):
        self.saved_to = filename


@pytest.fixture(autouse=True)
def restore_uiautomator2_logger():
    logger = logging.getLogger("uiautomator2")
    handlers = list(logger.handlers)
    level = logger.level
    propagate = logger.propagate
    disabled = logger.disabled

    yield

    for handler in logger.handlers:
        if handler not in handlers:
            handler.close()
    logger.handlers = handlers
    logger.setLevel(level)
    logger.propagate = propagate
    logger.disabled = disabled


def test_device_registry_reuses_device():
    device = Mock()
    connector = Mock(return_value=device)
    registry = DeviceRegistry(connector=connector)

    assert registry.get("serial-1", port=DEFAULT_SERVER_PORT) is device
    assert registry.get("serial-1", port=DEFAULT_SERVER_PORT) is device
    connector.assert_called_once_with("serial-1", port=DEFAULT_SERVER_PORT)


def test_screenshot_command_outputs_resolution(tmp_path, capsys):
    client = Mock()
    filename = tmp_path / "shot.png"
    client.request.return_value = {"filename": str(filename), "resolution": "1080x2400"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)) as ensure_server:
        main(["-s", "serial-1", "screenshot", "-p", "9009", str(filename)])

    ensure_server.assert_called_once_with("127.0.0.1", 17913)
    client.request.assert_called_once_with("screenshot", {
        "serial": "serial-1",
        "port": 9009,
        "filename": str(filename),
    })
    out = capsys.readouterr().out
    assert out.startswith("{\n  ")
    assert json.loads(out) == {
        "u2_code": "d.screenshot(%r)" % str(filename),
        "saved_to": str(filename),
        "resolution": "1080x2400",
    }


def test_server_screenshot_returns_resolution():
    image = FakeImage()
    device = Mock()
    device.screenshot.return_value = image
    registry = DeviceRegistry(connector=Mock(return_value=device))
    server = Mock()
    server.registry = registry
    handler = object.__new__(U2CliRequestHandler)
    handler.server = server

    result = handler._screenshot({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "filename": "shot.png"})

    assert result == {"filename": "shot.png", "resolution": "1080x2400"}
    assert image.saved_to == "shot.png"


def test_server_status_outputs_json(capsys):
    client = Mock()
    client.is_running.return_value = True
    client.status.return_value = {"host": "127.0.0.1", "port": 17913, "pid": 123}

    with patch("uiautomator2.agent_cli.__main__.U2CliClient", return_value=client):
        main(["server-status"])

    out = capsys.readouterr().out
    assert out.startswith("{\n  ")
    assert json.loads(out) == {
        "host": "127.0.0.1",
        "port": 17913,
        "pid": 123,
        "running": True,
    }


def test_missing_command_outputs_json_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("{\n  ")
    assert json.loads(err) == {
        "error": "command is required",
        "type": "ArgumentError",
    }


def test_help_has_no_json_option(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    assert "--json" not in capsys.readouterr().out
