#!/usr/bin/env python3
# coding: utf-8
#

import re
import os
import time
import argparse

import yaml
import bunch
import uiautomator2 as u2
from logzero import logger


CLICK = "click"
# swipe
SWIPE_UP = "swipe_up"
SWIPE_RIGHT = "swipe_right"
SWIPE_LEFT = "swipe_left"
SWIPE_DOWN = "swipe_down"

SCREENSHOT = "screenshot"
EXIST = "assert_exist"
WAIT = "wait"


def split_step(text: str):
    __alias = {
        "点击": CLICK,
        "上滑": SWIPE_UP,
        "右滑": SWIPE_RIGHT,
        "左滑": SWIPE_LEFT,
        "下滑": SWIPE_DOWN,
        "截图": SCREENSHOT,
        "存在": EXIST,
        "等待": WAIT,
    }

    for keyword in __alias.keys():
        if text.startswith(keyword):
            body = text[len(keyword):].strip()
            return __alias.get(keyword, keyword), body
    else:
        raise RuntimeError("Step unable to parse", text)


def read_file_content(path: str, mode:str = "r") -> str:
    with open(path, mode) as f:
        return f.read()

def run_step(cf: bunch.Bunch, app: u2.Session, step: str):
    logger.info("Step: %s", step)
    oper, body = split_step(step)
    logger.debug("parse as: %s %s", oper, body)

    if oper == CLICK:
        app.xpath(body).click()

    elif oper == SWIPE_RIGHT:
        app.xpath(body).swipe("right")
    elif oper == SWIPE_UP:
        app.xpath(body).swipe("up")
    elif oper == SWIPE_LEFT:
        app.xpath(body).swipe("left")
    elif oper == SWIPE_DOWN:
        app.xpath(body).swipe("down")

    elif oper == SCREENSHOT:
        output_dir = "./output"
        filename = "screen-%d.jpg" % int(time.time()*1000)
        if body:
            filename = body
        name_noext, ext = os.path.splitext(filename)
        if ext.lower() not in ['.jpg', '.jpeg', '.png']:
            ext = ".jpg"
        os.makedirs(cf.output_directory, exist_ok=True)
        filename = os.path.join(cf.output_directory, name_noext + ext)
        logger.debug("Save screenshot: %s", filename)
        app.screenshot().save(filename)

    elif oper == EXIST:
        assert app.xpath(body).wait(), body

    elif oper == WAIT:
        #if re.match("^[\d\.]+$")
        if body.isdigit():
            seconds = int(body)
            logger.info("Sleep %d seconds", seconds)
            time.sleep(seconds)
        else:
            app.xpath(body).wait()

    else:
        raise RuntimeError("Unhandled operation", oper)
    

def run_conf(d, conf_filename: str):
    d.healthcheck()
    d.xpath.when("允许").click()
    d.xpath.watch_background(2.0)

    cf = yaml.load(read_file_content(conf_filename), Loader=yaml.SafeLoader)
    default = {
        "output_directory": "output",
        "action_before_delay": 0,
        "action_after_delay": 0,
        "skip_cleanup": False,
    }
    for k, v in default.items():
        cf.setdefault(k, v)
    cf = bunch.Bunch(cf)

    print("Author:", cf.author)
    print("Description:", cf.description)
    print("Package:", cf.package)
    logger.debug("action_delay: %.1f / %.1f", cf.action_before_delay, cf.action_after_delay)

    app = d.session(cf.package)
    for step in cf.steps:
        time.sleep(cf.action_before_delay)
        run_step(cf, app, step)
        time.sleep(cf.action_after_delay)

    if not cf.skip_cleanup:
        app.close()


device = None
conf_filename = None

def test_entry():
    pass



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--command", help="run single step command")
    parser.add_argument("-s", "--serial", help="run single step command")
    parser.add_argument("conf_filename", default="test.yml", nargs="?", help="config filename")
    args = parser.parse_args()

    d = u2.connect(args.serial)
    if args.command:
        cf = bunch.Bunch({"output_directory": "output"})
        app = d.session()
        run_step(cf, app, args.command)

    else:
        run_conf(d, args.conf_filename)
