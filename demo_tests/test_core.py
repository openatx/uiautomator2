# coding: utf-8
# author: codeskyblue

from typing import Optional
import uiautomator2 as u2


def get_app_process_pid(d: u2.Device) -> Optional[int]:
    for line in d.shell("ps -u shell").output.splitlines():
        fields = line.split()
        if fields[-1] == 'app_process':
            pid = fields[1]
            return int(pid)
    return None


def kill_app_process(d: u2.Device) -> bool:
    pid = get_app_process_pid(d)
    if not pid:
        return False
    d.shell(f"kill {pid}")
    return True


def test_uiautomator_keeper(d: u2.Device):
    kill_app_process(d)
    d.sleep(.2)
    assert get_app_process_pid(d) is None
    d.shell('rm /data/local/tmp/u2.jar')
    
    d.start_uiautomator()
    assert get_app_process_pid(d) > 0
    
    d.stop_uiautomator()
    assert get_app_process_pid(d) is None


def test_debug(d: u2.Device):
    d.debug = True
    d.info
    