# coding: utf-8
#

from __future__ import absolute_import, print_function

import argparse
import hashlib
import json
import logging
import os
import re

import progress.bar
import requests
from logzero import logger
from retry import retry

import adbutils
import uiautomator2 as u2

from .init import Initer
from .version import __version__


def cmd_init(args):
    serial = args.serial or args.serial_optional
    if serial:
        device = adbutils.adb.device(serial)
        init = Initer(device)
        init.install()
    else:
        for device in adbutils.adb.iter_device():
            init = Initer(device, loglevel=logging.DEBUG)
            if args.addr:
                init.set_atx_agent_addr(args.addr)
            init.install()


def cmd_purge(args):
    """ remove minicap, minitouch, uiautomator ... """
    device = adbutils.adb.device(args.serial)
    init = Initer(device, loglevel=logging.DEBUG)
    init.uninstall()


def cmd_screenshot(args):
    d = u2.connect(args.serial)
    d.screenshot().save(args.filename)
    print("Save screenshot to %s" % args.filename)


def cmd_identify(args):
    d = u2.connect(args.serial)
    d.press("home")
    d.open_identify(args.theme)


def cmd_install(args):
    u = u2.connect(args.serial)
    pkg_name = u.app_install(args.url)
    print("Installed", pkg_name)


def cmd_uninstall(args):
    d = u2.connect(args.serial)
    if args.all:
        d.app_uninstall_all(verbose=True)
    else:
        for package_name in args.package_name:
            print("Uninstall \"%s\" " % package_name, end="", flush=True)
            ok = d.app_uninstall(package_name)
            print("OK" if ok else "FAIL")


def cmd_healthcheck(args):
    d = u2.connect(args.serial)
    d.healthcheck()


def cmd_start(args):
    d = u2.connect(args.serial)
    d.app_start(args.package_name)


def cmd_stop(args):
    d = u2.connect(args.serial)
    if args.all:
        d.app_stop_all()
        return

    for package_name in args.package_name:
        print("am force-stop \"%s\" " % package_name)
        d.app_stop(package_name)


def cmd_current(args):
    d = u2.connect(args.serial)
    print(json.dumps(d.app_current(), indent=4))


def cmd_doctor(args):
    d = adbutils.adb.device(args.serial)
    from .init import Initer
    init = Initer(d)
    logger.debug("sdk:%s abi:%s", init.sdk, init.abi)

    ok = True
    print("CHECK atx-agent")
    if init.is_atx_agent_outdated():
        print("\tFAIL")
        ok = False
        # logger.warning("atx-agent is invalid")
    else:
        version = init.check_atx_agent_version()
        print("\tGOOD: atx-agent version", version)

    print("CHECK uiautomator-apks")
    if init.is_apk_outdated():
        print("\tFAIL")
        logger.warning("apk is invalid")
        ok = False
    else:
        apk_debug = init._device.package_info("com.github.uiautomator")
        version = apk_debug['version_name']
        print("\tGOOD: com.github.uiautomator", version)
    
    if ok:
        print("CHECK jsonrpc")
        d = u2.connect(args.serial)
        # print(d.info)
        if d.alive:
            print("\tGOOD: d.info success")
        else:
            ok = False
    
    print("==> %s <==" % ("GOOD" if ok else "FAIL"))
    

def cmd_version(args):
    print("uiautomator2 version: %s" % __version__)


def cmd_console(args):
    import code
    import platform

    d = u2.connect(args.serial)
    model = d.shell("getprop ro.product.model").output.strip()
    serial = d.serial
    try:
        import IPython
        from traitlets.config import get_config
        c = get_config()
        c.InteractiveShellEmbed.colors = "neutral"
        IPython.embed(config=c, header="IPython -- d.info is ready")
    except ImportError:
        _vars = globals().copy()
        _vars.update(locals())
        shell = code.InteractiveConsole(_vars)
        shell.interact(banner="Python: %s\nDevice: %s(%s)" %
                       (platform.python_version(), model, serial))


_commands = [
    dict(action=cmd_version,
         command="version",
         help="show version"),
    dict(action=cmd_init,
         command="init",
         help="install enssential resources to device",
         flags=[
             dict(args=['--addr'], default='127.0.0.1:7912', help='atx-agent listen address'),
             dict(args=['--serial', '-s'], type=str, help='serial number'),
             dict(args=['serial_optional'],
                  nargs='?',
                  help='serial number, same as --serial'),
         ]),
    dict(action=cmd_screenshot,
         command="screenshot",
         help="take device screenshot",
         flags=[
             dict(args=['filename'],
                  nargs='?',
                  default="screenshot.jpg",
                  type=str,
                  help="output filename, jpg or png")
         ]),
    dict(action=cmd_identify,
         command="identify",
         help="quickly find your device by change device screen color",
         flags=[
             dict(args=['--theme'],
                  type=str,
                  default='red',
                  help="black or red")
         ]),
    dict(action=cmd_install,
         command="install",
         help="install packages",
         flags=[
             dict(args=["url"], help="package url"),
         ]),
    dict(action=cmd_uninstall,
         command="uninstall",
         help="uninstall packages",
         flags=[
             dict(args=["--all"],
                  action="store_true",
                  help="uninstall all packages"),
             dict(args=["package_name"], nargs="*", help="package name")
         ]),
    dict(action=cmd_healthcheck,
         command="healthcheck",
         help="recover uiautomator service"),
    dict(action=cmd_healthcheck, command="check",
         help="alias of healthcheck"),  # yapf: disable
    dict(action=cmd_start,
         command="start",
         help="start application",
         flags=[
             dict(args=["package_name"],
                  type=str,
                  nargs=None,
                  help="package name")
         ]),
    dict(action=cmd_stop,
         command="stop",
         help="stop application",
         flags=[
             dict(args=["--all"], action="store_true", help="stop all"),
             dict(args=["package_name"], nargs="*", help="package name")
         ]),
    dict(action=cmd_current,
         command="current",
         help="show current application"),
    dict(action=cmd_doctor,
         command='doctor',
         help='detect connect problem'),
    dict(action=cmd_console,
         command="console",
         help="launch interactive python console"),
    dict(action=cmd_purge,
        command="purge",
        help="remove minitouch, minicap, atx app etc, from device"),
]


def main():
    # yapf: disable
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-d", "--debug", action="store_true",
                        help="show log")
    parser.add_argument('-s', '--serial', type=str,
                        help='device serial number')

    subparser = parser.add_subparsers(dest='subparser')

    actions = {}
    for c in _commands:
        cmd_name = c['command']
        actions[cmd_name] = c['action']
        sp = subparser.add_parser(cmd_name, help=c.get('help'),
                                  formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        for f in c.get('flags', []):
            args = f.get('args')
            if not args:
                args = ['-'*min(2, len(n)) + n for n in f['name']]
            kwargs = f.copy()
            kwargs.pop('name', None)
            kwargs.pop('args', None)
            sp.add_argument(*args, **kwargs)

    args = parser.parse_args()
    if args.debug:
        logger.debug("args: %s", args)

    if args.subparser:
        actions[args.subparser](args)
        return

    parser.print_help()
    # yapf: enable


if __name__ == '__main__':
    # import logzero
    # logzero.loglevel(logging.INFO)
    main()
