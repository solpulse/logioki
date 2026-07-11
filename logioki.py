#!/usr/bin/env python3
"""Compatibility launcher; all command policy lives in :mod:`logioki_cli`."""

import sys


def __getattr__(name):
    """Temporary compatibility for legacy internal controller tests/views."""
    if name in {"WindowController", "LOGGER"}:
        from controller import LOGGER, WindowController

        return {"WindowController": WindowController, "LOGGER": LOGGER}[name]
    if name == "GLib":
        from gi.repository import GLib

        return GLib
    raise AttributeError(name)


def main(argv=None):
    from logioki_cli import main as cli_main

    return cli_main(sys.argv if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
