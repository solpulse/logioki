"""Dependency-light command-line entry point for Logioki."""

from __future__ import annotations

import argparse
import sys

import store


def _non_negative_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if seconds < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return seconds


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control and restore UVC webcam settings")
    parser.add_argument("--apply", action="store_true", help="restore settings without a GUI")
    parser.add_argument("--retry", type=_non_negative_seconds, default=0, metavar="SECONDS")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    parser = _parser()
    args, gui_arguments = parser.parse_known_args(argv[1:])
    if args.apply:
        if gui_arguments:
            parser.error(f"unrecognized arguments: {' '.join(gui_arguments)}")
        matched, result = store.apply_all(retry_seconds=args.retry)
        return 0 if matched and result.ok else 1
    if args.retry:
        parser.error("--retry requires --apply")

    try:
        from qml_app import main as gui_main
    except ModuleNotFoundError as exc:
        if not exc.name or not exc.name.startswith("PySide6"):
            raise
        parser.error("the graphical application requires PySide6; install logioki[gui]")
    return gui_main([argv[0], *gui_arguments])


if __name__ == "__main__":
    raise SystemExit(main())
