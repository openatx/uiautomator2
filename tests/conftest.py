# coding: utf-8

import adbutils
import uiautomator2 as u2
import pytest


@pytest.fixture(scope="module")
def d(device):
    _d = device
    #_d = u2.connect()
    _d.settings['operation_delay'] = (0.2, 0.2)
    _d.settings['operation_delay_methods'] = ['click', 'swipe']
    return _d


@pytest.fixture
def package_name():
    return "io.appium.android.apis"


@pytest.fixture(scope="function")
def sess(d, package_name) -> u2.Device:
    d.watcher.reset()
    
    d.app_start(package_name, stop=True)
    yield d


# run parallel
# py.test --tx "3*popen" --dist=load test_device.py -q --tb=line

def read_device_list() -> list:
    return [v.serial for v in adbutils.adb.device_list()]


def pytest_configure(config):
     # read device list if we are on the master
     if not hasattr(config, "slaveinput"):
        config.devlist = read_device_list()


# def pytest_configure_node(node):
#     # the master for each node fills slaveinput dictionary
#     # which pytest-xdist will transfer to the subprocess
#     serial = node.slaveinput["serial"] = node.config.devlist.pop()
#     node.config.devlist.insert(0, serial)


@pytest.fixture(scope="session")
def device(request):
    slaveinput = getattr(request.config, "slaveinput", None)
    if slaveinput is None: # single-process execution
        serial = read_device_list()[0]
    else: # running in a subprocess here
        serial = slaveinput["serial"]
    print("SERIAL:", serial)
    return u2.connect(serial)
