from unittest.mock import Mock

import pytest

from uiautomator2 import Device


@pytest.mark.parametrize('activity', ['.Settings', 'com.android.settings.Settings'])
def test_resolve_launcher(activity):
    device = Mock()
    device.shell.return_value = Mock(output='priority=0\ncom.android.settings/' + activity + '\n', exit_code=0)
    Device.app_start(device, 'com.android.settings', stop=True, wait=True)
    device.app_stop.assert_called_once_with('com.android.settings')
    assert device.shell.call_args_list[0].args[0] == [
        'cmd', 'package', 'resolve-activity', '--brief',
        '-a', 'android.intent.action.MAIN',
        '-c', 'android.intent.category.LAUNCHER', 'com.android.settings'
    ]
    assert device.shell.call_args.args[0][-2:] == ['-n', 'com.android.settings/' + activity]
    device.app_wait.assert_called_once_with('com.android.settings')


@pytest.mark.parametrize('output,code', [('', 0), ('No activity found', 0), ('other/.Main', 0), ('com.android.settings/', 0), ('com.android.settings/.Settings', 1)])
def test_resolution_falls_back(output, code):
    device = Mock()
    device.shell.return_value = Mock(output=output, exit_code=code)
    Device.app_start(device, 'com.android.settings', wait=True)
    assert device.shell.call_args.args[0][0] == 'monkey'
    device.app_wait.assert_called_once_with('com.android.settings')


@pytest.mark.parametrize('activity,use_monkey,command', [(None, True, 'monkey'), ('.Settings', True, 'monkey'), ('.Settings', False, 'am')])
def test_explicit_launch_bypasses_resolution(activity, use_monkey, command):
    device = Mock()
    Device.app_start(device, 'com.android.settings', activity=activity, use_monkey=use_monkey)
    assert device.shell.call_count == 1
    assert device.shell.call_args.args[0][0] == command
