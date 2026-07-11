"""Install and manage Logioki's per-user settings restore service."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "logioki"
SYSTEMCTL = next(
    (path for path in (Path("/usr/bin/systemctl"), Path("/bin/systemctl")) if path.is_file()),
    Path("/usr/bin/systemctl"),
)
SYSTEMD_UNIT = (
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "systemd"
    / "user"
    / "logioki-restore.service"
)
UNIT_NAME = "logioki-restore.service"
GUI_AUTOSTART_FILE = (
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "autostart"
    / "io.github.solpulse.Logioki.desktop"
)


def _systemd_quote(value: str) -> str:
    """Quote an ExecStart argument, including systemd specifier escaping."""
    if "\n" in value or "\r" in value:
        raise ValueError("systemd command arguments cannot contain newlines")
    value = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def _restore_command() -> list[str]:
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return [str(Path(appimage).resolve()), "--apply", "--retry=30"]
    return [sys.executable, str(APP_DIR / "logioki.py"), "--apply", "--retry=30"]


def _unit_contents(commandline: list[str] | None = None) -> str:
    command = " ".join(_systemd_quote(argument) for argument in commandline or _restore_command())
    return f"""[Unit]
Description=Logioki: restore webcam settings
After=graphical-session.target
ConditionPathExists=!{GUI_AUTOSTART_FILE}

[Service]
Type=oneshot
ExecStart={command}
AmbientCapabilities=
CapabilityBoundingSet=
KeyringMode=private
NoNewPrivileges=yes
PrivateNetwork=yes
PrivateTmp=yes
ProcSubset=pid
ProtectProc=invisible
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=-{_systemd_quote(str(SETTINGS_DIR))}
ProtectClock=yes
ProtectControlGroups=yes
ProtectHostname=yes
ProtectKernelLogs=yes
ProtectKernelModules=yes
ProtectKernelTunables=yes
RestrictAddressFamilies=AF_UNIX
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
SystemCallArchitectures=native
SystemCallErrorNumber=EPERM
SystemCallFilter=~@clock @cpu-emulation @debug @module @mount @obsolete @raw-io @reboot @swap
UMask=0077

[Install]
WantedBy=default.target
"""


def _systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SYSTEMCTL), "--user", *arguments],
        check=check,
        capture_output=True,
        text=True,
        timeout=15,
    )


def install_restore_service() -> tuple[bool, str | None]:
    """Atomically install and enable the per-user login restore service."""
    temporary_name = None
    try:
        SYSTEMD_UNIT.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=SYSTEMD_UNIT.parent,
            prefix=f".{SYSTEMD_UNIT.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(_unit_contents())
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, SYSTEMD_UNIT)
        temporary_name = None
        directory_fd = os.open(SYSTEMD_UNIT.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        _systemctl("daemon-reload")
        _systemctl("enable", UNIT_NAME)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        return False, detail.strip()
    finally:
        if temporary_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)
    return True, None


def remove_restore_service() -> tuple[bool, str | None]:
    """Disable and remove the per-user restore service."""
    errors: list[str] = []
    try:
        result = _systemctl("disable", UNIT_NAME, check=False)
        if result.returncode:
            errors.append(result.stderr.strip() or f"systemctl exited with {result.returncode}")
        SYSTEMD_UNIT.unlink(missing_ok=True)
        result = _systemctl("daemon-reload", check=False)
        if result.returncode:
            errors.append(result.stderr.strip() or f"systemctl exited with {result.returncode}")
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(str(exc))
    return (not errors, "; ".join(errors) or None)


def is_restore_service_enabled() -> bool:
    if not SYSTEMD_UNIT.exists():
        return False
    try:
        return _systemctl("is-enabled", "--quiet", UNIT_NAME, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
