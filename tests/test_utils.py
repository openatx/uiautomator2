# coding: utf-8
#

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