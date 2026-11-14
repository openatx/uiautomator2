from unittest.mock import Mock

import pytest
from adbutils import RunningAppInfo

from uiautomator2 import Device
from uiautomator2.exceptions import DeviceError


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


def test_floating_window_does_not_steal_current_app():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{8a7f2c1 #105 type=standard A=10234:org.telegram.messenger U=0 visible=false mode=fullscreen translucent=false sz=1}
    isSleeping=false
    topResumedActivity=ActivityRecord{6a3d5e1 u0 org.telegram.messenger/.LaunchActivity t105}
    Hist #0: ActivityRecord{6a3d5e1 u0 org.telegram.messenger/.LaunchActivity t105}
      app=ProcessRecord{93c2a11 4321:org.telegram.messenger/u0a234}
  * Task{9d9e1f0 #123 type=standard A=10123:com.example.app U=0 visible=true mode=fullscreen translucent=false sz=1}
    isSleeping=false
    topResumedActivity=ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t123}
    Hist #1: ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t123}
      app=ProcessRecord{8f6a9b3 12345:com.example.app/u0a123}
    Hist #0: ActivityRecord{11aa22b u0 com.example.app/.SettingsActivity t123}
      visible=false
"""
    assert app_current(output) == {
        'package': 'com.example.app',
        'activity': '.MainActivity',
        'pid': 12345,
    }


def test_secondary_display_is_not_reported_as_current():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #1 (activities from top to bottom):
  * Task{c1d2e3f #201 type=standard A=10345:org.telegram.messenger U=0 visible=true mode=fullscreen translucent=false sz=1}
    isSleeping=false
    topResumedActivity=ActivityRecord{d4e5f60 u0 org.telegram.messenger/.LaunchActivity t201}
    Hist #0: ActivityRecord{d4e5f60 u0 org.telegram.messenger/.LaunchActivity t201}
      app=ProcessRecord{e5f6071 5432:org.telegram.messenger/u0a345}
Display #0 (activities from top to bottom):
  * Task{9d9e1f0 #123 type=standard A=10123:com.example.app U=0 visible=true mode=fullscreen translucent=false sz=1}
    isSleeping=false
    topResumedActivity=ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t123}
    Hist #0: ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t123}
      app=ProcessRecord{8f6a9b3 12345:com.example.app/u0a123}
"""
    assert app_current(output)['package'] == 'com.example.app'


def test_primary_display_wins_when_it_is_printed_first():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{9d9e1f0 #123 type=standard A=10123:com.example.app U=0 visible=true mode=fullscreen translucent=false sz=1}
    topResumedActivity=ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t123}
Display #1 (activities from top to bottom):
  * Task{c1d2e3f #201 type=standard A=10345:org.telegram.messenger U=0 visible=true mode=fullscreen translucent=false sz=1}
    topResumedActivity=ActivityRecord{d4e5f60 u0 org.telegram.messenger/.LaunchActivity t201}
"""
    assert app_current(output)['package'] == 'com.example.app'


def test_android14_top_level_resumed_activity_is_used_when_task_has_no_header():
    # AOSP 14 prints the resumed activity before the task blocks, and the task
    # block itself has no topResumedActivity line.
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
mResumedActivity: ActivityRecord{10684b5 u0 app.ericn.myapp/.SecondActivity t1068}
RootTask #1068: type=standard mode=fullscreen
isSleeping=false
* Task{41d503 #1068 type=standard A=10287:app.ericn.myapp U=0 visible=true mode=fullscreen translucent=false sz=2}
mBounds=Rect(0, 0 - 0, 0)
affinity=10287:app.ericn.myapp
RootTask #100: type=home mode=fullscreen
* Task{77acb32 #100 type=home A=10291:com.android.launcher3 U=0 visible=false mode=fullscreen translucent=false sz=1}
Hist #1: ActivityRecord{10684b5 u0 app.ericn.myapp/.SecondActivity t1068}
Hist #0: ActivityRecord{da73511 u0 app.ericn.myapp/.MainActivity t1068}

Resumed activities in task display areas (from top to bottom):
Resumed: ActivityRecord{10684b5 u0 app.ericn.myapp/.SecondActivity t1068}

ResumedActivity: ActivityRecord{10684b5 u0 app.ericn.myapp/.SecondActivity t1068}
"""
    assert app_current(output) == {
        'package': 'app.ericn.myapp',
        'activity': '.SecondActivity',
        'pid': 0,
    }


def test_android10_dump_without_task_blocks():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  Stack #1:
    Task id #12
      TaskRecord{e64923a #12 A=com.example.app U=0 StackId=1 sz=2}
      Running activities (most recent first):
        TaskRecord{e64923a #12 A=com.example.app U=0 StackId=1 sz=2}
          Run #1: ActivityRecord{68c3212 u0 com.example.app/.SubActivity t12}
          Run #0: ActivityRecord{18177e0 u0 com.example.app/.MainActivity t12}

    mResumedActivity: ActivityRecord{68c3212 u0 com.example.app/.SubActivity t12}
    mLastPausedActivity: ActivityRecord{18177e0 u0 com.example.app/.MainActivity t12}
"""
    assert app_current(output) == {
        'package': 'com.example.app',
        'activity': '.SubActivity',
        'pid': 0,
    }


def test_old_dump_without_visibility_uses_first_task_block():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{aaa111 #1 type=standard A=10123:com.example.app U=0 mode=fullscreen sz=1}
    topResumedActivity=ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t1}
  * Task{bbb222 #2 type=standard A=10234:org.telegram.messenger U=0 mode=fullscreen sz=1}
    topResumedActivity=ActivityRecord{6a3d5e1 u0 org.telegram.messenger/.LaunchActivity t2}
"""
    assert app_current(output)['package'] == 'com.example.app'


def test_hidden_task_resumed_line_is_not_used_as_last_resort():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{9d9e1f0 #123 type=standard A=10123:com.example.app U=0 visible=true mode=fullscreen translucent=false sz=1}
    Hist #1: ActivityRecord{2f9f6a3 u0 com.example.app/.MainActivity t123}
  * Task{8a7f2c1 #105 type=standard A=10234:org.telegram.messenger U=0 visible=false mode=fullscreen translucent=false sz=1}
    topResumedActivity=ActivityRecord{6a3d5e1 u0 org.telegram.messenger/.LaunchActivity t105}
"""
    fallback = RunningAppInfo(package='com.android.systemui', activity='.Keyguard', pid=111)
    assert app_current(output, fallback)['package'] == 'com.android.systemui'


def test_all_tasks_hidden_falls_back_to_adbutils():
    output = """ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)
Display #0 (activities from top to bottom):
  * Task{8a7f2c1 #105 type=standard A=10234:org.telegram.messenger U=0 visible=false mode=fullscreen translucent=false sz=1}
    topResumedActivity=ActivityRecord{6a3d5e1 u0 org.telegram.messenger/.LaunchActivity t105}
"""
    fallback = RunningAppInfo(package='com.android.systemui', activity='.Keyguard', pid=111)
    assert app_current(output, fallback) == {
        'package': 'com.android.systemui',
        'activity': '.Keyguard',
        'pid': 111,
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
