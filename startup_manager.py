"""Toolkit-neutral login startup management for Logioki."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import service

AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "io.github.solpulse.Logioki.desktop"


def _desktop_exec_quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("desktop command arguments cannot contain newlines")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
    escaped = escaped.replace("$", "\\$")
    escaped = escaped.replace("%", "%%")
    return f'"{escaped}"'


def _gui_command() -> list[str]:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return [str(Path(appimage).resolve())]
    executable = shutil.which("logioki")
    if executable:
        return [executable]
    return [str(Path(sys.executable).resolve()), "-m", "logioki_cli"]


def _desktop_contents() -> str:
    command = " ".join(_desktop_exec_quote(argument) for argument in _gui_command())
    return "\n".join(
        (
            "[Desktop Entry]",
            "Type=Application",
            "Name=Logioki",
            f"Exec={command}",
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            "X-KDE-autostart-after=panel",
            "",
        )
    )


class StartupManager:
    """Expose independent restore and GUI login settings."""

    def __init__(self, portal_request=None):
        self._flatpak = bool(os.environ.get("FLATPAK_ID")) or Path("/.flatpak-info").is_file()
        self._portal_request = portal_request
        self._restore = False
        self._open_gui = False

    def load_state(self, restore: bool, open_gui: bool) -> None:
        """Seed persisted state used by the Flatpak portal coordinator."""
        self._restore = bool(restore)
        self._open_gui = bool(open_gui)

    def _request_flatpak(self, restore: bool, open_gui: bool) -> tuple[bool, str | None]:
        request = self._portal_request
        if request is None:
            from flatpak_portal import request_background

            request = request_background
        enabled = restore or open_gui
        executable = shutil.which("logioki") or "logioki"
        commandline = [executable]
        if restore and not open_gui:
            commandline.extend(("--apply", "--retry=30"))
        result = request(enabled, commandline)
        if result[0]:
            self._restore, self._open_gui = restore, open_gui
        return result

    def restore_enabled(self) -> bool:
        if self._flatpak:
            return self._restore
        return service.is_restore_service_enabled()

    def set_restore_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        if self._flatpak:
            return self._request_flatpak(enabled, self._open_gui)
        return service.install_restore_service() if enabled else service.remove_restore_service()

    def open_gui_enabled(self) -> bool:
        if self._flatpak:
            return self._open_gui
        return AUTOSTART_FILE.is_file()

    def set_open_gui_enabled(self, enabled: bool) -> tuple[bool, str | None]:
        if self._flatpak:
            return self._request_flatpak(self._restore, enabled)
        try:
            if not enabled:
                AUTOSTART_FILE.unlink(missing_ok=True)
                return True, None
            AUTOSTART_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary_name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=AUTOSTART_DIR,
                    prefix=f".{AUTOSTART_FILE.name}.",
                    delete=False,
                ) as temporary:
                    temporary_name = temporary.name
                    temporary.write(_desktop_contents())
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, AUTOSTART_FILE)
                temporary_name = None
            finally:
                if temporary_name:
                    Path(temporary_name).unlink(missing_ok=True)
            return True, None
        except OSError as exc:
            return False, exc.strerror or str(exc)
