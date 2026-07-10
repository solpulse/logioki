"""Settings, presets, and verified restore logic for Logioki."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import v4l2ctl
from v4l2ctl import TYPE_BOOL, TYPE_INT, TYPE_MENU

LOGGER = logging.getLogger(__name__)


CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "logioki"
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
SCHEMA_VERSION = 2

BUILTIN_PRESETS = (
    ("default", "Default"),
    ("streaming", "Streaming"),
    ("video-calls", "Video Calls"),
)


@dataclass(slots=True)
class RestoreResult:
    applied: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed

    def merge(self, other: RestoreResult, prefix: str | None = None) -> None:
        def namespaced(values):
            if prefix is None:
                return values
            return {f"{prefix}:{key}": value for key, value in values.items()}

        self.applied.update(namespaced(other.applied))
        self.skipped.update(namespaced(other.skipped))
        self.failed.update(namespaced(other.failed))


def _empty_data() -> dict[str, Any]:
    return {"version": SCHEMA_VERSION, "app": {"auto_restore": False}, "cameras": {}}


def _quarantine_corrupt_config(path: Path) -> None:
    """Preserve an unreadable settings file instead of overwriting it later."""
    suffix = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}"
    destination = path.with_name(f"{path.name}.corrupt-{suffix}")
    try:
        path.replace(destination)
    except OSError:
        LOGGER.exception("Could not preserve corrupt settings file %s", path)


def _validate_preset(camera_key: str, preset_id: Any, preset: Any) -> None:
    if not isinstance(preset_id, str) or not isinstance(preset, dict):
        raise ValueError(f"invalid preset in {camera_key}")
    if not isinstance(preset.get("controls", {}), dict):
        raise ValueError(f"preset controls for {camera_key}/{preset_id} must be an object")
    if "name" in preset and not isinstance(preset["name"], str):
        raise ValueError(f"preset name for {camera_key}/{preset_id} must be text")


def _validate_camera_entry(camera_key: Any, entry: Any) -> None:
    if not isinstance(camera_key, str) or not isinstance(entry, dict):
        raise ValueError("camera entries must be objects with string keys")
    if not isinstance(entry.get("controls", {}), dict):
        raise ValueError(f"controls for {camera_key} must be an object")
    presets = entry.get("presets", {})
    if not isinstance(presets, dict):
        raise ValueError(f"presets for {camera_key} must be an object")
    for preset_id, preset in presets.items():
        _validate_preset(camera_key, preset_id, preset)


def _validate_current_data(data: dict[str, Any]) -> dict[str, Any]:
    cameras = data.get("cameras")
    if not isinstance(cameras, dict):
        raise ValueError("settings cameras must be an object")
    if not isinstance(data.get("app"), dict):
        data["app"] = {}
    if not isinstance(data["app"].get("auto_restore", False), bool):
        raise ValueError("auto_restore must be a boolean")
    data["app"].setdefault("auto_restore", False)
    for camera_key, entry in cameras.items():
        _validate_camera_entry(camera_key, entry)
    return data


def _migrate_legacy_data(data: dict[str, Any]) -> dict[str, Any]:
    # Version 1 stored camera model names directly at the top level. Keep it
    # available until a matching camera is seen, then migrate it to a stable key.
    migrated = _empty_data()
    migrated["legacy_cameras"] = {
        key: value
        for key, value in data.items()
        if isinstance(value, dict) and isinstance(value.get("controls"), dict)
    }
    return migrated


def _normalize_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("settings root must be an object")
    version = data.get("version")
    if version == SCHEMA_VERSION:
        return _validate_current_data(data)
    if isinstance(version, int) and version > SCHEMA_VERSION:
        raise ValueError(
            f"settings schema {version} is newer than supported schema {SCHEMA_VERSION}"
        )
    return _migrate_legacy_data(data)


def load() -> dict[str, Any]:
    path = Path(CONFIG_FILE)
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return _empty_data()
    except json.JSONDecodeError:
        LOGGER.warning("Settings file is not valid JSON and will be preserved: %s", path)
        _quarantine_corrupt_config(path)
        return _empty_data()
    except OSError:
        LOGGER.exception("Could not read settings file: %s", path)
        return _empty_data()

    try:
        return _normalize_data(data)
    except ValueError:
        LOGGER.warning("Settings file has an invalid schema and will be preserved: %s", path)
        _quarantine_corrupt_config(path)
        return _empty_data()


def save(data: dict[str, Any]) -> None:
    directory = Path(CONFIG_DIR)
    target = Path(CONFIG_FILE)
    directory.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            os.chmod(temporary.name, 0o600)
            json.dump(data, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


def capture_controls(cam, defaults: bool = False) -> dict[str, int]:
    """Return a serializable control snapshot, omitting unreadable controls."""
    values = {}
    for ctrl in cam.controls:
        if getattr(ctrl, "read_only", False):
            continue
        if defaults:
            value = ctrl.default
        else:
            try:
                value = cam.get(ctrl.id)
            except OSError:
                continue
        values[str(ctrl.id)] = int(value)
    return values


def camera_entry(data: dict[str, Any], cam, create: bool = True) -> dict[str, Any] | None:
    """Get a camera entry, migrating the old model-name key when possible."""
    cameras = data.setdefault("cameras", {})
    entry = cameras.get(cam.key)
    if entry is None:
        legacy = data.get("legacy_cameras", {}).pop(cam.card, None)
        if legacy is not None:
            entry = legacy
            cameras[cam.key] = entry
        elif create:
            entry = {}
            cameras[cam.key] = entry
        else:
            return None
    entry["name"] = cam.card
    entry["device"] = cam.path
    if "controls" not in entry:
        entry["controls"] = capture_controls(cam)
    presets = entry.setdefault("presets", {})
    current = dict(entry["controls"])
    for preset_id, name in BUILTIN_PRESETS:
        if preset_id not in presets:
            controls = (
                capture_controls(cam, defaults=True) if preset_id == "default" else dict(current)
            )
            presets[preset_id] = {
                "name": name,
                "builtin": True,
                "controls": controls,
            }
    entry.setdefault("selected_preset", "streaming")
    return entry


def preset_items(entry: Mapping[str, Any]) -> list[tuple[str, str]]:
    presets = entry.get("presets", {})
    builtins = [
        (preset_id, presets[preset_id]["name"])
        for preset_id, _name in BUILTIN_PRESETS
        if preset_id in presets
    ]
    custom = sorted(
        (
            (key, value.get("name", key))
            for key, value in presets.items()
            if not value.get("builtin")
        ),
        key=lambda item: item[1].casefold(),
    )
    return builtins + custom


def unique_preset_id(entry: Mapping[str, Any], name: str) -> str:
    base = "-".join(name.casefold().split()) or "custom"
    base = "".join(ch for ch in base if ch.isalnum() or ch in "-_") or "custom"
    candidate = base
    number = 2
    while candidate in entry.get("presets", {}):
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def create_preset(entry: dict[str, Any], name: str, controls: Mapping[str, int]) -> str:
    name = " ".join(name.split()).strip()
    if not name:
        raise ValueError("Preset name cannot be empty")
    preset_id = unique_preset_id(entry, name)
    entry.setdefault("presets", {})[preset_id] = {
        "name": name,
        "builtin": False,
        "controls": dict(controls),
    }
    return preset_id


def update_preset(entry: dict[str, Any], preset_id: str, controls: Mapping[str, int]) -> None:
    preset = entry.get("presets", {}).get(preset_id)
    if preset is None:
        raise KeyError(preset_id)
    if preset_id == "default":
        raise ValueError("The camera-default preset cannot be overwritten")
    preset["controls"] = dict(controls)


def delete_preset(entry: dict[str, Any], preset_id: str) -> None:
    preset = entry.get("presets", {}).get(preset_id)
    if preset is None:
        raise KeyError(preset_id)
    if preset.get("builtin"):
        raise ValueError("Built-in presets cannot be deleted")
    del entry["presets"][preset_id]


def _parse_saved_controls(cam, saved_values, result: RestoreResult):
    by_id = {c.id: c for c in cam.controls}
    items = []
    for key, value in saved_values.items():
        try:
            ctrl_id = int(key)
        except (TypeError, ValueError):
            result.skipped[str(key)] = "invalid control identifier"
            continue
        if ctrl_id not in by_id:
            result.skipped[str(key)] = "control is not exposed by this camera"
            continue
        try:
            value = int(value)
        except (TypeError, ValueError):
            result.failed[str(key)] = "saved value is not an integer"
            continue
        items.append((ctrl_id, value))
    return by_id, items


def _apply_control_pass(cam, by_id, items, allowed_types, result: RestoreResult) -> None:
    for ctrl_id, value in items:
        ctrl = by_id[ctrl_id]
        key = str(ctrl_id)
        if ctrl.type not in allowed_types:
            continue
        if getattr(ctrl, "read_only", False):
            result.skipped[key] = "control is read-only"
            continue
        if ctrl.inactive:
            result.skipped[key] = "control is inactive in the selected mode"
            continue
        try:
            cam.set(ctrl_id, value)
            actual = cam.get(ctrl_id)
        except OSError as exc:
            result.failed[key] = exc.strerror or str(exc)
            continue
        if actual != value:
            result.failed[key] = f"requested {value}, camera reports {actual}"
        else:
            result.applied[key] = actual


def apply_to_camera(cam, saved_values: Mapping[str, Any]) -> RestoreResult:
    """Push values to the device and verify every active write by reading it back."""
    result = RestoreResult()
    by_id, items = _parse_saved_controls(cam, saved_values, result)

    # Apply auto/manual switches before the values whose active state they gate.
    cam.refresh_flags()
    _apply_control_pass(cam, by_id, items, (TYPE_BOOL, TYPE_MENU), result)
    cam.refresh_flags()
    _apply_control_pass(cam, by_id, items, (TYPE_INT,), result)
    return result


def apply_all(quiet: bool = False, retry_seconds: int = 0) -> tuple[int, RestoreResult]:
    """Restore saved settings to connected cameras, optionally waiting for them."""
    deadline = time.monotonic() + max(0, retry_seconds)
    while True:
        data = load()
        cameras = v4l2ctl.list_cameras()
        matched = 0
        aggregate = RestoreResult()
        messages = []
        for cam in cameras:
            try:
                entry = camera_entry(data, cam, create=False)
                values = entry.get("controls") if entry else None
                if values:
                    matched += 1
                    result = apply_to_camera(cam, values)
                    aggregate.merge(result, prefix=cam.key)
                    messages.append(
                        f"{cam.card} ({cam.path}): {len(result.applied)} applied, "
                        f"{len(result.skipped)} skipped, {len(result.failed)} failed"
                    )
            finally:
                cam.close()
        should_retry = (not matched or bool(aggregate.failed)) and time.monotonic() < deadline
        if not should_retry:
            if not quiet:
                for message in messages:
                    print(f"logioki: {message}")
                for ctrl_id, reason in aggregate.failed.items():
                    print(f"logioki: control {ctrl_id}: {reason}", file=sys.stderr)
                if not matched:
                    print("logioki: no saved camera is currently available", file=sys.stderr)
            return matched, aggregate
        time.sleep(min(2, max(0, deadline - time.monotonic())))
