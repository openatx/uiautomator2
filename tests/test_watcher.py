# coding: utf-8
#

import uiautomator2 as u2


def test_watch_context(sess: u2.Device):
    with sess.watch_context(builtin=True) as ctx:
        ctx.when("App").click()
        
        sess(text='Menu').click()
        assert sess(text='Inflate from XML').wait()


def teardown_function(d: u2.Device):
    print("Teardown", d)
