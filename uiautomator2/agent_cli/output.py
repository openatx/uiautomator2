# coding: utf-8

from __future__ import absolute_import, print_function

import pathlib
import sys
from typing import Any, Dict, Optional

from PIL import Image

def _absolute_filename(filename: str) -> str:
    path = pathlib.Path(filename).expanduser()
    if not path.is_absolute():
        path = pathlib.Path.cwd() / path
    return str(path)

def _output_result(result: Any = None, u2_code: Optional[str] = None, extra: Optional[Dict[str, Any]] = None):
    device_serial = extra.get("device_serial") if extra else None
    if device_serial is None and isinstance(result, dict):
        device_serial = result.get("device_serial")
    if device_serial:
        print("device_serial: %s" % device_serial)
    if u2_code:
        print("u2_code: %s" % u2_code)
    if extra:
        for key, value in extra.items():
            if key == "device_serial":
                continue
            print("%s: %s" % (key, value))
    if result is not None:
        if isinstance(result, dict):
            for key, value in result.items():
                if key == "device_serial":
                    continue
                print("%s: %s" % (key, value))
        elif isinstance(result, list):
            for value in result:
                print(value)
        elif isinstance(result, str) and "\n" in result:
            _output_text(result)
        else:
            print("result: %s" % result)

def _output_text(result: str):
    sys.stdout.write(result)
    if not result.endswith("\n"):
        sys.stdout.write("\n")

def _output_message(message: str, extra: Optional[Dict[str, Any]] = None):
    print(message)
    if extra:
        for key, value in extra.items():
            print("%s: %s" % (key, value))

def _output_error(exc: BaseException):
    _output_error_message(str(exc))

def _output_error_message(message: str):
    print("error: %s" % message, file=sys.stderr)

def _image_resolution(filename: str) -> Optional[str]:
    try:
        with Image.open(filename) as image:
            width, height = image.size
    except OSError:
        return None
    return "%sx%s" % (width, height)

def _parse_key(key: str):
    try:
        return int(key)
    except ValueError:
        return key
