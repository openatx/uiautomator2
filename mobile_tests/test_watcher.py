# coding: utf-8
#

import uiautomator2 as u2


def test_watch_context(dev: u2.Device):
    with dev.watch_context(builtin=True) as ctx:
        ctx.when("App").click()
        
        dev(text='Menu').click()
        assert dev(text='Inflate from XML').wait()


def teardown_function(d: u2.Device):
    print("Teardown", d)
