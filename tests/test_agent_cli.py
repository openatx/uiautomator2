# coding: utf-8

import logging
from http.client import IncompleteRead
from unittest.mock import Mock, patch

import pytest

from uiautomator2.agent_cli import client as agent_client
from uiautomator2.agent_cli.__main__ import main
from uiautomator2.agent_cli.server import DeviceRegistry, U2CliRequestHandler, hierarchy_to_text
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


def test_device_registry_rebinds_default_when_bound_device_goes_offline():
    devices = {"A": object(), "B": object()}
    online_serials = ["A"]
    connector = Mock(side_effect=lambda serial, port: devices[serial])
    registry = DeviceRegistry(
        connector=connector,
        device_lister=lambda: list(online_serials),
        default_serial_getter=lambda: online_serials[0],
    )

    assert registry.get(port=DEFAULT_SERVER_PORT) is devices["A"]

    online_serials[:] = ["A", "B"]
    assert registry.get(port=DEFAULT_SERVER_PORT) is devices["A"]

    online_serials[:] = ["B"]
    assert registry.get(port=DEFAULT_SERVER_PORT) is devices["B"]
    assert [call.args[0] for call in connector.call_args_list] == ["A", "B"]


def test_screenshot_command_outputs_resolution(tmp_path, capsys):
    client = Mock()
    filename = tmp_path / "shot.png"
    client.request.return_value = {"filename": str(filename), "resolution": "1080x2400", "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)) as ensure_server:
        main(["-s", "serial-1", "screenshot", "-p", "9009", str(filename)])

    ensure_server.assert_called_once_with("127.0.0.1", 17913)
    client.request.assert_called_once_with("screenshot", {
        "serial": "serial-1",
        "port": 9009,
        "filename": str(filename),
    })
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "device_serial: serial-1"
    assert "u2_code: d.screenshot(%r)" % str(filename) in out
    assert "saved_to: %s" % filename in out
    assert "device_serial: serial-1" in out
    assert "resolution: 1080x2400" in out


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

    assert result == {"filename": "shot.png", "resolution": "1080x2400", "device_serial": "serial-1"}
    assert image.saved_to == "shot.png"


def test_dump_hierarchy_command_outputs_result(capsys):
    client = Mock()
    client.request.return_value = {
        "content": 'TextView "Settings" #pkg:id/title [10,20,200,80] click',
        "device_serial": "serial-1",
    }

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["-s", "serial-1", "dump-hierarchy", "-p", "9009", "--compressed", "--max-depth", "7"])

    client.request.assert_called_once_with("dump_hierarchy", {
        "serial": "serial-1",
        "port": 9009,
        "compressed": True,
        "max_depth": 7,
        "raw": False,
        "output": None,
    })
    out = capsys.readouterr().out
    assert out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.dump_hierarchy(compressed=True, max_depth=7)",
        'TextView "Settings" #pkg:id/title [10,20,200,80] click',
        "",
    ])


def test_dump_hierarchy_command_outputs_saved_path(tmp_path, capsys):
    client = Mock()
    output = tmp_path / "hierarchy.txt"
    client.request.return_value = {"filename": str(output), "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["dump-hierarchy", "--raw", "--output", str(output)])

    assert client.request.call_args.args[0] == "dump_hierarchy"
    assert client.request.call_args.args[1]["raw"] is True
    assert client.request.call_args.args[1]["output"] == str(output)
    assert capsys.readouterr().out == "device_serial: serial-1\nu2_code: d.dump_hierarchy()\nsaved_to: %s\n" % output


def test_hierarchy_to_text_simplifies_xml():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node class="android.widget.TextView" text="Settings" resource-id="pkg:id/title" bounds="[10,20][200,80]" clickable="true" />
  <node class="android.widget.TextView" text="Hidden" bounds="[0,0][0,0]" />
  <node class="android.widget.Button" text="OK" content-desc="confirm" bounds="[20,100][160,180]" enabled="false" />
</hierarchy>
"""

    assert hierarchy_to_text(xml) == "\n".join([
        'android.widget.TextView "Settings" #pkg:id/title [10,20,200,80] click',
        'android.widget.Button "OK" desc="confirm" [20,100,160,180] disabled',
    ])


def test_server_dump_hierarchy_returns_compact_text():
    device = Mock()
    device.dump_hierarchy.return_value = """<hierarchy>
  <node class="android.widget.TextView" text="Settings" bounds="[10,20][200,80]" />
</hierarchy>"""
    registry = DeviceRegistry(connector=Mock(return_value=device))
    server = Mock()
    server.registry = registry
    handler = object.__new__(U2CliRequestHandler)
    handler.server = server

    result = handler._dump_hierarchy({
        "serial": "serial-1",
        "port": DEFAULT_SERVER_PORT,
        "compressed": True,
        "max_depth": 7,
        "raw": False,
    })

    device.dump_hierarchy.assert_called_once_with(compressed=True, max_depth=7)
    assert result == {"content": 'android.widget.TextView "Settings" [10,20,200,80]', "device_serial": "serial-1"}


def test_app_current_command_outputs_text(capsys):
    client = Mock()
    client.request.return_value = {
        "package": "com.example.app",
        "activity": ".MainActivity",
        "pid": 1234,
        "device_serial": "serial-1",
    }

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["-s", "serial-1", "app-current", "-p", "9009"])

    client.request.assert_called_once_with("app_current", {
        "serial": "serial-1",
        "port": 9009,
    })
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.app_current()",
        "package: com.example.app",
        "activity: .MainActivity",
        "pid: 1234",
        "",
    ])


def test_app_current_command_accepts_underscore_alias(capsys):
    client = Mock()
    client.request.return_value = {"package": "com.example.app", "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["app_current"])

    assert "u2_code: d.app_current()" in capsys.readouterr().out


def test_server_app_current_returns_device_serial():
    device = Mock()
    device.app_current.return_value = {"package": "com.example.app", "activity": ".MainActivity"}
    registry = DeviceRegistry(connector=Mock(return_value=device))
    server = Mock()
    server.registry = registry
    handler = object.__new__(U2CliRequestHandler)
    handler.server = server

    result = handler._app_current({"serial": "serial-1", "port": DEFAULT_SERVER_PORT})

    device.app_current.assert_called_once_with()
    assert result == {
        "package": "com.example.app",
        "activity": ".MainActivity",
        "device_serial": "serial-1",
    }


def test_device_info_command_outputs_text(capsys):
    client = Mock()
    client.request.return_value = {"model": "Pixel", "sdk": 35, "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["device-info", "-p", "9009"])

    client.request.assert_called_once_with("device_info", {"serial": None, "port": 9009})
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.device_info",
        "model: Pixel",
        "sdk: 35",
        "",
    ])


def test_window_size_command_outputs_text(capsys):
    client = Mock()
    client.request.return_value = {"width": 1080, "height": 2400, "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["window-size", "-p", "9009"])

    client.request.assert_called_once_with("window_size", {"serial": None, "port": 9009})
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.window_size()",
        "width: 1080",
        "height: 2400",
        "",
    ])


def test_window_size_command_accepts_underscore_alias(capsys):
    client = Mock()
    client.request.return_value = {"width": 1080, "height": 2400, "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["window_size"])

    assert "u2_code: d.window_size()" in capsys.readouterr().out


def test_app_start_command_requests_server(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["app-start", "--activity", ".Main", "--wait", "--stop", "com.example"])

    client.request.assert_called_once_with("app_start", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "package": "com.example",
        "activity": ".Main",
        "wait": True,
        "stop": True,
    })
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.app_start('com.example', activity='.Main', wait=True, stop=True)",
        "",
    ])


def test_app_list_command_outputs_packages(capsys):
    client = Mock()
    client.request.return_value = {"packages": ["com.example.one", "com.example.two"], "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["app-list", "--filter", "-3"])

    client.request.assert_called_once_with("app_list", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "filter": "-3",
    })
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.app_list('-3')",
        "com.example.one",
        "com.example.two",
        "",
    ])


def test_app_stop_command_supports_package_and_all(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["app-stop", "com.example"])
        main(["app-stop", "--all"])

    assert client.request.call_args_list[0].args == ("app_stop", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "package": "com.example",
        "all": False,
    })
    assert client.request.call_args_list[1].args == ("app_stop", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "package": None,
        "all": True,
    })
    out = capsys.readouterr().out
    assert "u2_code: d.app_stop('com.example')" in out
    assert "u2_code: d.app_stop_all()" in out


def test_app_install_uninstall_clear_commands(capsys):
    client = Mock()
    client.request.side_effect = [
        {"result": "com.example", "device_serial": "serial-1"},
        {"result": True, "device_serial": "serial-1"},
        {"device_serial": "serial-1"},
    ]

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["app-install", "demo.apk"])
        main(["app-uninstall", "com.example"])
        main(["app-clear", "com.example"])

    assert client.request.call_args_list[0].args == ("app_install", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "apk": "demo.apk",
    })
    assert client.request.call_args_list[1].args == ("app_uninstall", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "package": "com.example",
    })
    assert client.request.call_args_list[2].args == ("app_clear", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "package": "com.example",
    })
    out = capsys.readouterr().out
    assert "u2_code: d.app_install('demo.apk')" in out
    assert "result: com.example" in out
    assert "u2_code: d.app_uninstall('com.example')" in out
    assert "result: True" in out
    assert "u2_code: d.app_clear('com.example')" in out


def test_shell_command_outputs_response(capsys):
    client = Mock()
    client.request.return_value = {"output": "hello\n", "exit_code": 0, "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["shell", "--timeout", "5", "echo", "hello"])

    client.request.assert_called_once_with("shell", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "command": "echo hello",
        "timeout": 5,
    })
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d.shell('echo hello', timeout=5)",
        "exit_code: 0",
        "hello",
        "",
    ])


def test_system_ui_commands_request_server(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["open-notification"])
        main(["open-quick-settings"])
        main(["open-url", "https://example.com"])

    assert client.request.call_args_list[0].args == ("open_notification", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
    })
    assert client.request.call_args_list[1].args == ("open_quick_settings", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
    })
    assert client.request.call_args_list[2].args == ("open_url", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "url": "https://example.com",
    })
    out = capsys.readouterr().out
    assert "u2_code: d.open_notification()" in out
    assert "u2_code: d.open_quick_settings()" in out
    assert "u2_code: d.open_url('https://example.com')" in out


def test_press_command_parses_key_and_keycode(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["press", "home"])
        main(["press", "66"])

    assert client.request.call_args_list[0].args == ("press", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "key": "home",
    })
    assert client.request.call_args_list[1].args == ("press", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "key": 66,
    })
    out = capsys.readouterr().out
    assert "u2_code: d.press('home')" in out
    assert "u2_code: d.press(66)" in out


def test_send_keys_command_defaults_to_clear_and_supports_no_clear(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["send-keys", "hello"])
        main(["send_keys", "--no-clear", "world"])

    assert client.request.call_args_list[0].args == ("send_keys", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "text": "hello",
        "clear": True,
    })
    assert client.request.call_args_list[1].args == ("send_keys", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "text": "world",
        "clear": False,
    })
    out = capsys.readouterr().out
    assert "u2_code: d.send_keys('hello', clear=True)" in out
    assert "u2_code: d.send_keys('world', clear=False)" in out


def test_clear_text_command_requests_server(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["clear-text"])
        main(["clear_text"])

    assert client.request.call_args_list[0].args == ("clear_text", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
    })
    assert client.request.call_args_list[1].args == ("clear_text", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
    })
    assert "u2_code: d.clear_text()" in capsys.readouterr().out


def test_server_app_and_device_methods_return_device_serial():
    device = Mock()
    device.device_info = {"model": "Pixel"}
    device.window_size.return_value = (1080, 2400)
    device.app_list.return_value = ["com.example"]
    device.app_install.return_value = "com.example"
    device.app_uninstall.return_value = True
    shell_response = Mock()
    shell_response.output = "ok\n"
    shell_response.exit_code = 0
    device.shell.return_value = shell_response
    registry = DeviceRegistry(connector=Mock(return_value=device))
    server = Mock()
    server.registry = registry
    handler = object.__new__(U2CliRequestHandler)
    handler.server = server

    assert handler._device_info({"serial": "serial-1", "port": DEFAULT_SERVER_PORT}) == {
        "model": "Pixel",
        "device_serial": "serial-1",
    }
    assert handler._app_list({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "filter": "-3"}) == {
        "packages": ["com.example"],
        "device_serial": "serial-1",
    }
    assert handler._window_size({"serial": "serial-1", "port": DEFAULT_SERVER_PORT}) == {
        "width": 1080,
        "height": 2400,
        "device_serial": "serial-1",
    }
    assert handler._app_install({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "apk": "demo.apk"}) == {
        "result": "com.example",
        "device_serial": "serial-1",
    }
    assert handler._app_uninstall({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "package": "com.example"}) == {
        "result": True,
        "device_serial": "serial-1",
    }
    assert handler._shell({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "command": "echo ok", "timeout": 5}) == {
        "output": "ok\n",
        "exit_code": 0,
        "device_serial": "serial-1",
    }
    handler._app_start({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "package": "com.example", "wait": True})
    handler._app_stop({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "package": "com.example"})
    handler._app_clear({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "package": "com.example"})
    handler._open_notification({"serial": "serial-1", "port": DEFAULT_SERVER_PORT})
    handler._open_quick_settings({"serial": "serial-1", "port": DEFAULT_SERVER_PORT})
    handler._open_url({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "url": "https://example.com"})
    assert handler._press({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "key": "home"}) == {
        "device_serial": "serial-1",
    }
    assert handler._send_keys({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "text": "hello", "clear": True}) == {
        "device_serial": "serial-1",
    }
    assert handler._clear_text({"serial": "serial-1", "port": DEFAULT_SERVER_PORT}) == {
        "device_serial": "serial-1",
    }
    device.app_start.assert_called_once_with("com.example", wait=True)
    device.app_stop.assert_called_once_with("com.example")
    device.app_clear.assert_called_once_with("com.example")
    device.open_notification.assert_called_once_with()
    device.open_quick_settings.assert_called_once_with()
    device.open_url.assert_called_once_with("https://example.com")
    device.press.assert_called_once_with("home")
    device.send_keys.assert_called_once_with("hello", clear=True)
    device.clear_text.assert_called_once_with()


def test_coordinate_gesture_commands_request_server(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["click", "10", "20"])
        main(["double-click", "--duration", "0.2", "10", "20"])
        main(["long-click", "--duration", "0.8", "10", "20"])
        main(["swipe", "--steps", "20", "10", "20", "80", "90"])
        main(["drag", "--duration", "0.7", "10", "20", "80", "90"])

    assert client.request.call_args_list[0].args == ("click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "x": 10.0,
        "y": 20.0,
    })
    assert client.request.call_args_list[1].args == ("double_click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "x": 10.0,
        "y": 20.0,
        "duration": 0.2,
    })
    assert client.request.call_args_list[2].args == ("long_click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "x": 10.0,
        "y": 20.0,
        "duration": 0.8,
    })
    assert client.request.call_args_list[3].args == ("swipe", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "fx": 10.0,
        "fy": 20.0,
        "tx": 80.0,
        "ty": 90.0,
        "duration": 0.5,
        "steps": 20,
    })
    assert client.request.call_args_list[4].args == ("drag", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "sx": 10.0,
        "sy": 20.0,
        "ex": 80.0,
        "ey": 90.0,
        "duration": 0.7,
    })
    out = capsys.readouterr().out
    assert "u2_code: d.click(10.0, 20.0)" in out
    assert "u2_code: d.double_click(10.0, 20.0, duration=0.2)" in out
    assert "u2_code: d.long_click(10.0, 20.0, duration=0.8)" in out
    assert "u2_code: d.swipe(10.0, 20.0, 80.0, 90.0, steps=20)" in out
    assert "u2_code: d.drag(10.0, 20.0, 80.0, 90.0, duration=0.7)" in out


def test_direction_swipe_command_requests_server(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["swipe", "--scale", "0.8", "--steps", "20", "up"])
        main(["swipe", "forward"])

    assert client.request.call_args_list[0].args == ("swipe", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "direction": "up",
        "scale": 0.8,
        "duration": 0.5,
        "steps": 20,
    })
    assert client.request.call_args_list[1].args == ("swipe", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "direction": "up",
        "scale": 0.9,
        "duration": 0.5,
        "steps": None,
    })
    out = capsys.readouterr().out
    assert "u2_code: d.swipe_ext('up', scale=0.8, steps=20)" in out
    assert "u2_code: d.swipe_ext('up', scale=0.9, duration=0.5)" in out


def test_selector_commands_request_server(capsys):
    client = Mock()
    client.request.side_effect = [
        {"device_serial": "serial-1"},
        {"device_serial": "serial-1"},
        {"result": True, "device_serial": "serial-1"},
        {"result": False, "device_serial": "serial-1"},
        {"device_serial": "serial-1"},
    ]

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main(["click", "--text", "Settings", "--timeout", "5"])
        main(["long-click", "--resource-id", "pkg:id/button", "--duration", "0.8", "--timeout", "5"])
        main(["exists", "--text", "Settings", "--timeout", "2"])
        main(["wait", "--text", "Settings", "--gone", "--timeout", "2"])
        main(["scroll", "--scrollable", "--to-text", "Target"])

    assert client.request.call_args_list[0].args == ("click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"text": "Settings"},
        "timeout": 5.0,
    })
    assert client.request.call_args_list[1].args == ("long_click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"resourceId": "pkg:id/button"},
        "duration": 0.8,
        "timeout": 5.0,
    })
    assert client.request.call_args_list[2].args == ("selector_exists", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"text": "Settings"},
        "timeout": 2.0,
    })
    assert client.request.call_args_list[3].args == ("selector_wait", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"text": "Settings"},
        "timeout": 2.0,
        "gone": True,
    })
    assert client.request.call_args_list[4].args == ("selector_scroll", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"scrollable": True},
        "direction": "vert",
        "action": "forward",
        "max_swipes": None,
        "to_text": "Target",
    })
    out = capsys.readouterr().out
    assert "u2_code: d(text='Settings').click(timeout=5.0)" in out
    assert "u2_code: d(resourceId='pkg:id/button').long_click(duration=0.8, timeout=5.0)" in out
    assert "u2_code: d(text='Settings').exists(timeout=2.0)" in out
    assert "result: True" in out
    assert "u2_code: d(text='Settings').wait_gone(timeout=2.0)" in out
    assert "result: False" in out
    assert "u2_code: d(scrollable=True).scroll.vert.to(text='Target')" in out


def test_child_selector_command_supports_mixed_parent_and_child_conditions(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main([
            "click",
            "--text",
            "Parent",
            "--resource-id",
            "pkg:id/parent",
            "--child-text",
            "Child",
            "--child-resource-id",
            "pkg:id/child",
            "--timeout",
            "5",
        ])

    client.request.assert_called_once_with("click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"text": "Parent", "resourceId": "pkg:id/parent"},
        "child_selectors": [{"text": "Child", "resourceId": "pkg:id/child"}],
        "timeout": 5.0,
    })
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d(text='Parent', resourceId='pkg:id/parent').child(text='Child', resourceId='pkg:id/child').click(timeout=5.0)",
        "",
    ])


def test_repeated_child_selector_builds_chain(capsys):
    client = Mock()
    client.request.return_value = {"device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.ensure_server", return_value=(client, True)):
        main([
            "click",
            "--text",
            "A",
            "--child",
            "text=B",
            "resourceId=pkg:id/b",
            "--child",
            "text=C",
            "className=android.widget.TextView",
            "clickable=true",
        ])

    client.request.assert_called_once_with("click", {
        "serial": None,
        "port": DEFAULT_SERVER_PORT,
        "selector": {"text": "A"},
        "child_selectors": [
            {"text": "B", "resourceId": "pkg:id/b"},
            {"text": "C", "className": "android.widget.TextView", "clickable": True},
        ],
        "timeout": 3.0,
    })
    assert capsys.readouterr().out == "\n".join([
        "device_serial: serial-1",
        "u2_code: d(text='A').child(text='B', resourceId='pkg:id/b').child(text='C', className='android.widget.TextView', clickable=True).click(timeout=3.0)",
        "",
    ])


def test_child_selector_requires_parent_selector(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["exists", "--child-text", "Child"])

    assert exc.value.code == 1
    assert capsys.readouterr().err == "error: at least one parent selector option is required when child selector is used\n"


def test_server_gesture_and_selector_methods_return_device_serial():
    device = Mock()
    ui_object = Mock()
    child_object = Mock()
    ui_object.exists = True
    ui_object.wait.return_value = True
    ui_object.wait_gone.return_value = False
    scroll_vert = Mock()
    ui_object.scroll.vert = scroll_vert
    ui_object.child.return_value = child_object
    device.return_value = ui_object
    registry = DeviceRegistry(connector=Mock(return_value=device))
    server = Mock()
    server.registry = registry
    handler = object.__new__(U2CliRequestHandler)
    handler.server = server

    assert handler._click({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "x": 1, "y": 2}) == {"device_serial": "serial-1"}
    assert handler._double_click({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "x": 1, "y": 2, "duration": 0.2}) == {"device_serial": "serial-1"}
    assert handler._long_click({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "x": 1, "y": 2, "duration": 0.8}) == {"device_serial": "serial-1"}
    assert handler._swipe({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "fx": 1, "fy": 2, "tx": 3, "ty": 4, "steps": 20}) == {"device_serial": "serial-1"}
    assert handler._swipe({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "direction": "up", "scale": 0.8, "duration": 0.3}) == {"device_serial": "serial-1"}
    assert handler._drag({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "sx": 1, "sy": 2, "ex": 3, "ey": 4, "duration": 0.7}) == {"device_serial": "serial-1"}
    assert handler._click({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "selector": {"text": "Settings"}, "timeout": 5}) == {"device_serial": "serial-1"}
    assert handler._selector_exists({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "selector": {"text": "Settings"}}) == {"result": True, "device_serial": "serial-1"}
    assert handler._selector_wait({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "selector": {"text": "Settings"}, "timeout": 2}) == {"result": True, "device_serial": "serial-1"}
    assert handler._selector_scroll({"serial": "serial-1", "port": DEFAULT_SERVER_PORT, "selector": {"scrollable": True}, "direction": "vert", "action": "forward", "to_text": "Target"}) == {"device_serial": "serial-1"}
    assert handler._click({
        "serial": "serial-1",
        "port": DEFAULT_SERVER_PORT,
        "selector": {"text": "Parent", "resourceId": "pkg:id/parent"},
        "child_selectors": [
            {"text": "Child", "resourceId": "pkg:id/child"},
            {"text": "GrandChild"},
        ],
        "timeout": 5,
    }) == {"device_serial": "serial-1"}

    device.click.assert_called_once_with(1.0, 2.0)
    device.double_click.assert_called_once_with(1.0, 2.0, duration=0.2)
    device.long_click.assert_called_once_with(1.0, 2.0, duration=0.8)
    device.swipe.assert_called_once_with(1.0, 2.0, 3.0, 4.0, steps=20)
    device.swipe_ext.assert_called_once_with("up", scale=0.8, duration=0.3)
    device.drag.assert_called_once_with(1.0, 2.0, 3.0, 4.0, duration=0.7)
    device.assert_any_call(text="Settings")
    device.assert_any_call(text="Parent", resourceId="pkg:id/parent")
    ui_object.click.assert_called_once_with(timeout=5)
    ui_object.child.assert_called_once_with(text="Child", resourceId="pkg:id/child")
    child_object.child.assert_called_once_with(text="GrandChild")
    child_object.child.return_value.click.assert_called_once_with(timeout=5)
    ui_object.wait.assert_called_once_with(timeout=2.0)
    scroll_vert.to.assert_called_once_with(text="Target")


def test_ensure_server_restarts_incompatible_server():
    fake_client = Mock()
    fake_client.status.return_value = {"protocol_version": 1}
    fake_client.is_running.side_effect = [False, True]
    process = Mock()
    process.poll.return_value = None

    with patch("uiautomator2.agent_cli.client.U2CliClient", return_value=fake_client), patch(
        "uiautomator2.agent_cli.client.start_server_process", return_value=process
    ) as start_server_process:
        client, started = agent_client.ensure_server(timeout=1.0)

    assert client is fake_client
    assert started is True
    fake_client.request.assert_called_once_with("server.stop", timeout=2.0)
    start_server_process.assert_called_once_with("127.0.0.1", 17913)


def test_start_server_process_uses_agent_cli_module():
    with patch("uiautomator2.agent_cli.client.subprocess.Popen") as popen:
        agent_client.start_server_process("127.0.0.1", 17913)

    command = popen.call_args.args[0]
    assert command[:3] == [agent_client.sys.executable, "-m", "uiautomator2.agent_cli"]


def test_client_request_treats_incomplete_read_as_server_not_running():
    client = agent_client.U2CliClient()

    with patch("uiautomator2.agent_cli.client.request.urlopen", side_effect=IncompleteRead(b"", 42)):
        with pytest.raises(agent_client.ServerNotRunningError):
            client.request("server.status")


def test_server_status_outputs_text(capsys):
    client = Mock()
    client.is_running.return_value = True
    client.status.return_value = {"host": "127.0.0.1", "port": 17913, "pid": 123, "device_serial": "serial-1"}

    with patch("uiautomator2.agent_cli.__main__.U2CliClient", return_value=client):
        main(["server-status"])

    out = capsys.readouterr().out
    assert out.splitlines()[0] == "device_serial: serial-1"
    assert "host: 127.0.0.1" in out
    assert "port: 17913" in out
    assert "pid: 123" in out
    assert "device_serial: serial-1" in out
    assert "running: True" in out


def test_missing_command_outputs_json_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err == "error: command is required\n"


def test_unexpected_cli_error_does_not_print_traceback(capsys):
    with patch("uiautomator2.agent_cli.__main__.ensure_server", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit) as exc:
            main(["device-info"])

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert err == "error: boom\n"
    assert "Traceback" not in err


def test_help_has_no_json_option(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--json" not in out
    assert "==SUPPRESS==" not in out
    assert "usage: u2cli [global options] <command> [command options]" in out
    assert "global options:" in out
    assert "server commands:" in out
    assert "device commands:" in out
    assert "window-size (window_size)" in out
    assert "app commands:" in out
    assert "input commands:" in out
    assert "selector commands:" in out
    assert "system ui commands:" in out
    assert "app-current (app_current)" in out
    assert "{server,start-server" not in out


def test_subcommand_help_has_grouped_options(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["app-start", "--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "server options:" in out
    assert "device options:" in out
    assert "command options:" in out
    assert "--server-host" in out
    assert "-p PORT, --port PORT" in out
    assert "--activity ACTIVITY" in out


def test_selector_subcommand_help_has_selector_groups(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["exists", "--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "server options:" in out
    assert "device options:" in out
    assert "command options:" in out
    assert "selector options:" in out
    assert "child selector options:" in out
    assert "--text TEXT" in out
    assert "--child-text CHILD_TEXT" in out
    assert "--child KEY=VALUE [KEY=VALUE ...]" in out
