"""Dependency-light command-line entry point for Logioki."""

from __future__ import annotations

import argparse
import sys

import store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control and restore UVC webcam settings")
    parser.add_argument("--apply", action="store_true", help="restore settings without a GUI")
    parser.add_argument("--retry", type=int, default=0, metavar="SECONDS")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args, gtk_arguments = _parser().parse_known_args(argv[1:])
    if args.apply:
        matched, result = store.apply_all(retry_seconds=max(0, args.retry))
        return 0 if matched and result.ok else 1
    if args.retry:
        _parser().error("--retry requires --apply")

    from logioki import App

    return App().run([argv[0], *gtk_arguments])


if __name__ == "__main__":
    raise SystemExit(main())
