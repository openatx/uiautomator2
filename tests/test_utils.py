# coding: utf-8
#

import pytest
from uiautomator2 import utils

def test_list2cmdline():
    testdata = [
        [("echo", "hello"), "echo hello"],
        [("echo", "hello&world"), "echo 'hello&world'"],
        [("What's", "your", "name?"), """'What'"'"'s' your 'name?'"""]
    ]
    for args, expect in testdata:
        cmdline = utils.list2cmdline(args)
        assert cmdline == expect, "Args: %s, Expect: %s, Got: %s" % (args, expect, cmdline)


def test_inject_call():
    def foo(a, b, c=2):
        return a*100+b*10+c
    
    ret = utils.inject_call(foo, a=2, b=4)
    assert ret == 242

    with pytest.raises(TypeError):
        utils.inject_call(foo, 2)