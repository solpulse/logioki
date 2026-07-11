#!/usr/bin/env python3
"""Application launcher; all command policy lives in :mod:`logioki_cli`."""

import sys


def main(argv=None):
    from logioki_cli import main as cli_main

    return cli_main(sys.argv if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
