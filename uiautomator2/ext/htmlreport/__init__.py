# coding: utf-8
#

from __future__ import print_function

import functools
import inspect
import json
import os
import shutil
import sys
import time
import types
import uiautomator2
from PIL import ImageDraw


def mark_point(im, x, y):
    """
    Mark position to show which point clicked

    Args:
        im: pillow.Image
    """
    draw = ImageDraw.Draw(im)
    w, h = im.size
    draw.line((x, 0, x, h), fill='red', width=5)
    draw.line((0, y, w, y), fill='red', width=5)
    r = min(im.size) // 40
    draw.ellipse((x - r, y - r, x + r, y + r), fill='red')
    r = min(im.size) // 50
    draw.ellipse((x - r, y - r, x + r, y + r), fill='white')
    del draw
    return im


class HTMLReport(object):
    def __init__(self, driver, target_dir='report'):
        self._driver = driver
        self._target_dir = target_dir
        self._steps = []
        self._copy_assets()
        self._flush()

    def _copy_assets(self):
        # py3 can use os.makedirs(dst, exist_ok=True), but py2 cannot
        if not os.path.exists(self._target_dir):
            os.makedirs(self._target_dir)

        sdir = os.path.dirname(os.path.abspath(__file__))
        for file in ['index.html', 'simplehttpserver.py', 'start.bat']:
            src = os.path.join(sdir, 'assets', file)
            dst = os.path.join(self._target_dir, file)
            shutil.copyfile(src, dst)

    def _record_screenshot(self, pos=None):
        """
        Save screenshot and add record into record.json
        
        Example record data:
        {
            "time": "2017/1/2 10:20:30",
            "code": "d.click(100, 800)",
            "screenshot": "imgs/demo.jpg"
        }
        """
        im = self._driver.screenshot()
        if pos:
            x, y = pos
            im = mark_point(im, x, y)
            im.thumbnail((800, 800))
        relpath = os.path.join('imgs', 'img-%d.jpg' % (time.time() * 1000))
        abspath = os.path.join(self._target_dir, relpath)
        dstdir = os.path.dirname(abspath)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)
        im.save(abspath)
        self._addtosteps(dict(screenshot=relpath))

    def _addtosteps(self, data):
        """
        Args:
            data: dict used to save into record.json
        """
        codelines = []
        for stk in inspect.stack()[1:]:
            filename = stk[1]
            try:
                filename = os.path.relpath(filename)
            except ValueError:  # Windows: maybe on other driver, eg: C:/ F:/
                continue
            if filename.find("/site-packages/") != -1:  # Linux
                continue
            if filename.startswith(".."):  # only select files under curdir
                continue
            # --- stack ---
            # 0: the frame object
            # 1: the filename
            # 2: the line number of the current line
            # 3: the function name
            # 4: a list of lines of context from the source code
            # 5: the index of the current line within that list.
            codeline = '%s:%d\n  %s' % (filename, stk[2],
                                        ''.join(stk[4] or []).strip())
            codelines.append(codeline)
        code = '\n'.join(codelines)

        steps = self._steps
        base_data = {
            'time': time.strftime("%H:%M:%S"),
            'code': code,
        }
        base_data.update(data)
        steps.append(base_data)
        self._flush()

    def _flush(self):
        record_file = os.path.join(self._target_dir, 'record.json')
        with open(record_file, 'wb') as f:
            f.write(json.dumps({'steps': self._steps}).encode('utf-8'))

    def _patch_instance_func(self, obj, name, newfunc):
        """ patch a.funcname to new func """
        oldfunc = getattr(obj, name)
        print("mock", oldfunc)
        newfunc = functools.wraps(oldfunc)(newfunc)
        newfunc.oldfunc = oldfunc
        setattr(obj, name, types.MethodType(newfunc, obj))

    def _patch_class_func(self, obj, funcname, newfunc):
        """ patch A.funcname to new func """
        oldfunc = getattr(obj, funcname)
        if hasattr(oldfunc, 'oldfunc'):
            raise RuntimeError("function: %s.%s already patched before" %
                               (obj, funcname))
        newfunc = functools.wraps(oldfunc)(newfunc)
        newfunc.oldfunc = oldfunc
        setattr(obj, funcname, newfunc)

    def _unpatch_func(self, obj, funcname):
        curfunc = getattr(obj, funcname)
        if hasattr(curfunc, 'oldfunc'):
            setattr(obj, funcname, curfunc.oldfunc)
            return True

    def patch_click(self):
        """
        Record every click operation into report.
        """

        def _mock_click(obj, x, y):
            x, y = obj.pos_rel2abs(x, y)
            self._record_screenshot((x, y))  # write image and record.json
            return obj.click.oldfunc(obj, x, y)

        def _mock_long_click(obj, x, y, duration=None):
            x, y = obj.pos_rel2abs(x, y)
            self._record_screenshot((x, y))  # write image and record.json
            return obj.long_click.oldfunc(obj, x, y, duration)

        self._patch_class_func(uiautomator2.Session, 'click', _mock_click)
        self._patch_class_func(uiautomator2.Session, 'long_click',
                               _mock_long_click)

    def unpatch_click(self):
        """
        Remove record for click operation
        """
        self._unpatch_func(uiautomator2.Session, 'click')
        self._unpatch_func(uiautomator2.Session, 'long_click')