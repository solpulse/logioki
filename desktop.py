"""Desktop-environment detection without importing a UI toolkit."""

import os
import sys


def detect_desktop() -> str:
    forced = os.environ.get("LOGIOKI_DESKTOP_STYLE", "").lower()
    if forced in ("gnome", "kde", "macos"):
        return forced
    if sys.platform == "darwin":
        return "macos"
    values = (
        os.environ.get("XDG_CURRENT_DESKTOP", ""),
        os.environ.get("XDG_SESSION_DESKTOP", ""),
        os.environ.get("DESKTOP_SESSION", ""),
    )
    desktop = ":".join(values).lower()
    if os.environ.get("KDE_FULL_SESSION") or "kde" in desktop or "plasma" in desktop:
        return "kde"
    return "gnome"
