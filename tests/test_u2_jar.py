# coding: utf-8
#

import contextlib
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from adbutils import FileInfo

from uiautomator2.core import DEFAULT_JAR_PATH, BasicUiautomatorServer, get_jar_path, launch_uiautomator

DEVICE_DIR_MODE = 0o040755
DEVICE_FILE_MODE = 0o100644


def file_info(mode: int, size: int, path: str) -> FileInfo:
    exists = mode != 0
    return FileInfo(mode=mode, size=size, mtime=datetime.now() if exists else None, path=path)


@pytest.fixture
def local_jar(tmp_path):
    """Stand-in for the packaged assets/u2.jar, which is not in the repo"""
    path = tmp_path / "u2.jar"
    path.write_bytes(b"jar")

    @contextlib.contextmanager
    def fake_resource(filename):
        assert filename == "assets/u2.jar"
        yield path

    with patch("uiautomator2.core.with_package_resource", fake_resource):
        yield path


@pytest.fixture
def mock_server(local_jar):
    """BasicUiautomatorServer that never talks to a device"""
    mock_dev = Mock()
    with patch.object(BasicUiautomatorServer, "__init__", return_value=None):
        server = BasicUiautomatorServer(None)
    server._dev = mock_dev
    server._device_server_port = 9008
    server._jar_path = DEFAULT_JAR_PATH
    return server, mock_dev


class TestGetJarPath:

    def test_default(self, monkeypatch):
        monkeypatch.delenv("U2_JAR_PATH", raising=False)
        assert get_jar_path() == "/data/local/tmp/u2.jar"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("U2_JAR_PATH", "/data/local/tmp/u2dir/u2.jar")
        assert get_jar_path() == "/data/local/tmp/u2dir/u2.jar"

    def test_empty_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("U2_JAR_PATH", "")
        assert get_jar_path() == DEFAULT_JAR_PATH

    def test_init_stores_jar_path(self, monkeypatch):
        """The path is resolved once, before the server starts"""
        monkeypatch.setenv("U2_JAR_PATH", "/data/local/tmp/custom/u2.jar")
        with patch.object(BasicUiautomatorServer, "start_uiautomator"):
            server = BasicUiautomatorServer(Mock())
        assert server._jar_path == "/data/local/tmp/custom/u2.jar"


class TestSetupJar:

    def test_directory_is_removed_before_push(self, mock_server):
        """A directory at the jar path makes adb push write into it, so remove it first"""
        server, mock_dev = mock_server
        calls = []
        mock_dev.shell.side_effect = lambda args, **kwargs: calls.append(("shell", list(args)))
        mock_dev.sync.push.side_effect = lambda src, dst, **kwargs: calls.append(("push", dst))
        mock_dev.sync.stat.side_effect = [
            file_info(DEVICE_DIR_MODE, 4096, server._jar_path),
            file_info(0, 0, server._jar_path),
        ]

        server._setup_jar()

        assert calls == [
            ("shell", ["rm", "-rf", "/data/local/tmp/u2.jar"]),
            ("shell", ["mkdir", "-p", "/data/local/tmp"]),
            ("push", "/data/local/tmp/u2.jar"),
        ]

    def test_regular_file_is_not_removed(self, mock_server):
        """Only a directory triggers rm -rf"""
        server, mock_dev = mock_server
        mock_dev.sync.stat.side_effect = [
            file_info(DEVICE_FILE_MODE, 1, server._jar_path),
            file_info(DEVICE_FILE_MODE, 1, server._jar_path),
        ]

        server._setup_jar()

        # only mkdir for the parent, never rm -rf
        assert [c[0][0][0] for c in mock_dev.shell.call_args_list] == ["mkdir"]
        mock_dev.sync.push.assert_called_once()

    def test_up_to_date_file_is_not_pushed(self, mock_server):
        """Same size means the jar is already there, no rm and no push"""
        server, mock_dev = mock_server
        size = 3
        mock_dev.sync.stat.return_value = file_info(DEVICE_FILE_MODE, size, server._jar_path)

        server._setup_jar()

        mock_dev.sync.push.assert_not_called()

    def test_custom_path_used_for_push(self, mock_server, monkeypatch):
        """U2_JAR_PATH is honoured by _setup_jar, its parent is created"""
        monkeypatch.setenv("U2_JAR_PATH", "/data/local/tmp/other/u2.jar")
        server, mock_dev = mock_server
        server._jar_path = get_jar_path()
        mock_dev.sync.stat.side_effect = [
            file_info(0, 0, server._jar_path),
            file_info(0, 0, server._jar_path),
        ]

        server._setup_jar()

        mock_dev.shell.assert_called_once_with(["mkdir", "-p", "/data/local/tmp/other"])
        assert mock_dev.sync.push.call_args[0][1] == "/data/local/tmp/other/u2.jar"


class TestLaunchUiautomator:

    def test_default_classpath(self):
        mock_dev = Mock()
        mock_dev.shell.return_value = Mock()
        launch_uiautomator(mock_dev, 9008)
        cmd = mock_dev.shell.call_args[0][0]
        assert "CLASSPATH='/data/local/tmp/u2.jar'" in cmd
        assert "-p 9008" in cmd

    def test_custom_classpath(self):
        """The same custom path that was pushed is used in CLASSPATH"""
        mock_dev = Mock()
        mock_dev.shell.return_value = Mock()
        launch_uiautomator(mock_dev, 9009, "/data/local/tmp/u2 dir/u2.jar")
        cmd = mock_dev.shell.call_args[0][0]
        assert "CLASSPATH='/data/local/tmp/u2 dir/u2.jar'" in cmd
        assert "-p 9009" in cmd
