# coding: utf-8
#

import os
import io
import uiautomator2 as u2


def test_push_and_pull(d: u2.Device):
    device_target = "/data/local/tmp/hello.txt"
    content = b"hello world"

    d.push(io.BytesIO(content), device_target)
    d.pull(device_target, "tmpfile-hello.txt")
    with open("tmpfile-hello.txt", "rb") as f:
        assert f.read() == content
    os.unlink("tmpfile-hello.txt")
