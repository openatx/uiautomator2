#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Created on Wed Mar 20 2024 14:51:03 by codeskyblue
"""

import uiautomator2 as u2


def test_import():
    u2.Device
    u2.connect
    u2.connect_usb
    u2.Device.app_install
    u2.Device.app_uninstall
    u2.Device.app_current
    u2.Device.app_list
    u2.Device.shell
    u2.Device.send_keys
    u2.Device.click
    u2.Device.swipe
    u2.Device.dump_hierarchy
    u2.Device.freeze_rotation
    u2.Device.open_notification
    u2.Device.info
    u2.Device.xpath
    u2.Device.clipboard
    u2.Device.orientation