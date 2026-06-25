# coding: utf-8

from __future__ import absolute_import, print_function

import sys

import click

from uiautomator2.agent_cli.commands import cli
from uiautomator2.agent_cli.output import _output_error_message


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    try:
        exit_code = cli.main(args=list(argv), prog_name="u2cli", standalone_mode=False)
        if exit_code is not None:
            sys.exit(exit_code)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
    except click.ClickException as e:
        _output_error_message(e.format_message())
        sys.exit(e.exit_code)


if __name__ == "__main__":
    main()
