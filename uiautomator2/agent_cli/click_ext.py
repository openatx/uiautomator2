# coding: utf-8

from __future__ import absolute_import, print_function

import click
from click.parser import normalize_opt

# Repeat from __main__.py to avoid circular import; kept in sync manually
_HELP_CATEGORIES = [
    ("server commands", ["server", "start-server", "kill-server", "server-status"]),
    ("device commands", ["device-info", "window-size", "screenshot", "dump-hierarchy", "app-current", "shell"]),
    ("app commands", ["app-start", "app-list", "app-stop", "app-install", "app-uninstall", "app-clear"]),
    ("input commands", ["press", "send-keys", "clear-text", "click", "double-click", "long-click", "swipe", "drag"]),
    ("selector commands", ["exists", "wait", "scroll"]),
    ("system ui commands", ["open-notification", "open-quick-settings", "open-url"]),
]


class CategorizedGroup(click.Group):
    """A click.Group that shows commands grouped into categories."""

    def format_commands(self, ctx, formatter):
        commands = self.commands
        shown = set()
        for i, (title, command_names) in enumerate(_HELP_CATEGORIES):
            rows = []
            for name in command_names:
                if name in commands:
                    shown.add(name)
                    rows.append((name, commands[name].help or ""))
            if rows:
                if i > 0:
                    formatter.write_paragraph()
                with formatter.section("  %s" % title):
                    formatter.write_dl(rows)
        other = sorted(set(commands) - shown)
        if other:
            formatter.write_paragraph()
            with formatter.section("  other commands:"):
                formatter.write_dl([(name, commands[name].help or "") for name in other])


class ChildSelectorOption(click.Option):
    """Multi-token parsing for --child KEY=VALUE [KEY=VALUE ...]"""

    def add_to_parser(self, parser, ctx):
        super(ChildSelectorOption, self).add_to_parser(parser, ctx)
        for option in self.opts:
            parser_option = parser._long_opt.get(normalize_opt(option, ctx))
            if parser_option is None:
                continue
            process = parser_option.process

            def process_child(value, state, process=process):
                values = [value]
                while state.rargs and not _is_option_token(state.rargs[0], parser):
                    values.append(state.rargs.pop(0))
                process(tuple(values), state)

            parser_option.process = process_child


def _is_option_token(token: str, parser) -> bool:
    return len(token) > 1 and token[:1] in parser._opt_prefixes
