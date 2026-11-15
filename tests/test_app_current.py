from pathlib import Path
from unittest.mock import Mock

import pytest
from adbutils import RunningAppInfo

from uiautomator2 import Device
from uiautomator2.exceptions import DeviceError

FIXTURES = Path(__file__).parent / 'fixtures' / 'dumpsys'


def dumpsys(name):
    # Fixtures are real `adb shell dumpsys activity activities` excerpts; see
    # fixtures/dumpsys/README.md for devices, states and public sources.
    return (FIXTURES / name).read_text(encoding='utf-8')


def make_device(output, fallback=None):
    device = Mock()
    device.shell.return_value = Mock(output=output, exit_code=0)
    device.adb_device.app_current.return_value = fallback
    return device


def app_current(output, fallback=None):
    device = make_device(output, fallback)
    info = Device.app_current(device)
    assert device.shell.call_args.args[0] == ['dumpsys', 'activity', 'activities']
    return info


def test_background_app_is_not_current():
    # Android 14: Settings is visible while Chrome is still alive in a
    # visible=false task. Chrome is not resumed, so its block only has
    # mLastPausedActivity; the visible task must still be the one returned.
    assert app_current(dumpsys('android14-settings-foreground.txt')) == {
        'package': 'com.android.settings',
        'activity': '.Settings',
        'pid': 3574,
    }


def test_secondary_display_is_not_current():
    # Android 14 with an overlay display: Android prints Display #2 (Chrome)
    # before Display #0 (Settings), and both tasks are visible. app_current()
    # describes the primary display, so Settings must win.
    assert app_current(dumpsys('android14-multi-display.txt')) == {
        'package': 'com.android.settings',
        'activity': '.Settings',
        'pid': 3574,
    }


def test_primary_display_without_resumed_activity_falls_back():
    # Screen-off dump: the visible launcher task on Display #0 has only
    # mLastPausedActivity. The only ResumedActivity line in the tail belongs to
    # Chrome on Display #2, which must not be used as a stale fallback.
    fallback = RunningAppInfo(package='com.android.systemui', activity='.Keyguard', pid=111)
    assert app_current(dumpsys('android14-primary-display-without-resumed.txt'), fallback) == {
        'package': 'com.android.systemui',
        'activity': '.Keyguard',
        'pid': 111,
    }


def test_android13_top_level_resumed_activity_is_used():
    # Real Android 13+ dump: mResumedActivity is printed before the task blocks
    # and the task has no topResumedActivity= line.
    assert app_current(dumpsys('android13-top-level-resumed.txt')) == {
        'package': 'app.ericn.myapp',
        'activity': '.SecondActivity',
        'pid': 0,
    }


def test_android10_dump_without_task_blocks():
    # Real Android 10 style dump: Stack/TaskRecord output with no Task{ block,
    # so the first mResumedActivity line is the answer.
    assert app_current(dumpsys('android10-stack.txt')) == {
        'package': 'android.tplink.sjj.teststack',
        'activity': '.FirstActivity',
        'pid': 0,
    }


def test_unparseable_output_falls_back_to_adbutils():
    fallback = RunningAppInfo(package='com.example.app', activity='.MainActivity', pid=1234)
    assert app_current('', fallback) == {
        'package': 'com.example.app',
        'activity': '.MainActivity',
        'pid': 1234,
    }


def test_no_foreground_app_raises_device_error():
    with pytest.raises(DeviceError):
        app_current('ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)\n', None)
