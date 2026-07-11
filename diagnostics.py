"""Redacted diagnostics and bounded rotating logs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "logioki"
LOG_FILE = LOG_DIR / "logioki.log"


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def configure_logging() -> None:
    try:
        LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=512 * 1024, backupCount=3)
    except OSError:
        logging.getLogger(__name__).warning("Local diagnostic logging is unavailable")
        return
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def redact(value: str) -> str:
    home = str(Path.home())
    value = value.replace(home, "~")

    def replace_serial(match):
        digest = hashlib.sha256(match.group(2).encode()).hexdigest()[:10]
        return f"{match.group(1)}redacted-{digest}"

    return re.sub(r"(usb:[^:\s]+:[^:\s]+:)([^\s,;]+)", replace_serial, value)


def redact_identity(value: str) -> str:
    if value.startswith("bus:"):
        digest = hashlib.sha256(value.encode()).hexdigest()[:10]
        return f"bus:redacted-{digest}"
    return redact(value)


def camera_report(
    camera,
    preview: dict,
    errors: list[str],
    firmware: dict | None = None,
    control_values: dict[str, int] | None = None,
) -> dict:
    identity = getattr(camera, "key", "")
    usb = identity.split(":")[1:3] if identity.startswith("usb:") else []
    control_values = control_values or {}
    controls = [
        {
            "id": str(control.id),
            "name": control.name,
            "supported": True,
            "read_only": control.read_only,
            "inactive": control.inactive,
            "current": control_values.get(str(control.id)),
        }
        for control in camera.controls
    ]
    unsupported = [
        {"id": str(control.id), "name": control.name, "reason": control.reason}
        for control in getattr(camera, "unsupported_controls", ())
    ]
    firmware = firmware or {
        "available": False,
        "version": "Unavailable",
        "status": "Not reported by this camera",
    }
    return {
        "camera": {
            "model": camera.card,
            "identity": redact_identity(identity),
            "usb_id": ":".join(usb) if usb else "Unavailable",
            "driver_path": redact(camera.path),
            "driver": getattr(camera, "driver", "Unavailable"),
            "bus": redact(getattr(camera, "bus_info", "Unavailable")),
            "firmware": firmware["version"],
        },
        "controls": controls,
        "supported_controls": controls,
        "unsupported_controls": unsupported,
        "preview": preview,
        "firmware": firmware,
        "recent_errors": [redact(item) for item in errors[-20:]],
    }


def export_report(path: str, report: dict) -> None:
    target = Path(path)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
