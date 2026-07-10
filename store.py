"""Settings, presets, and verified restore logic for Logioki."""
from dataclasses import dataclass, field
import json
import os
import time


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


@dataclass
class RestoreResult:
    applied: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)
    failed: dict = field(default_factory=dict)

    @property
    def ok(self):
        return not self.failed

    def merge(self, other):
        self.applied.update(other.applied)
        self.skipped.update(other.skipped)
        self.failed.update(other.failed)


def _empty_data():
    return {"version": SCHEMA_VERSION, "app": {"auto_restore": True}, "cameras": {}}


def load():
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _empty_data()
    if not isinstance(data, dict):
        return _empty_data()
    if data.get("version") == SCHEMA_VERSION and isinstance(data.get("cameras"), dict):
        if not isinstance(data.get("app"), dict):
            data["app"] = {}
        data["app"].setdefault("auto_restore", True)
        return data
    # Version 1 stored camera model names directly at the top level. Keep it
    # available until a matching camera is seen, then migrate it to a stable key.
    migrated = _empty_data()
    migrated["legacy_cameras"] = {
        key: value for key, value in data.items()
        if isinstance(value, dict) and "controls" in value
    }
    return migrated


def save(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_FILE)


def capture_controls(cam, defaults=False):
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


def camera_entry(data, cam, create=True):
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
    entry.setdefault("controls", capture_controls(cam))
    presets = entry.setdefault("presets", {})
    current = dict(entry["controls"])
    for preset_id, name in BUILTIN_PRESETS:
        if preset_id not in presets:
            controls = capture_controls(cam, defaults=True) if preset_id == "default" else dict(current)
            presets[preset_id] = {
                "name": name,
                "builtin": True,
                "controls": controls,
            }
    entry.setdefault("selected_preset", "streaming")
    return entry


def preset_items(entry):
    presets = entry.get("presets", {})
    builtins = [
        (preset_id, presets[preset_id]["name"])
        for preset_id, _name in BUILTIN_PRESETS if preset_id in presets
    ]
    custom = sorted(
        ((key, value.get("name", key)) for key, value in presets.items()
         if not value.get("builtin")),
        key=lambda item: item[1].casefold(),
    )
    return builtins + custom


def unique_preset_id(entry, name):
    base = "-".join(name.casefold().split()) or "custom"
    base = "".join(ch for ch in base if ch.isalnum() or ch in "-_") or "custom"
    candidate = base
    number = 2
    while candidate in entry.get("presets", {}):
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def create_preset(entry, name, controls):
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


def update_preset(entry, preset_id, controls):
    preset = entry.get("presets", {}).get(preset_id)
    if preset is None:
        raise KeyError(preset_id)
    if preset_id == "default":
        raise ValueError("The camera-default preset cannot be overwritten")
    preset["controls"] = dict(controls)


def delete_preset(entry, preset_id):
    preset = entry.get("presets", {}).get(preset_id)
    if preset is None:
        raise KeyError(preset_id)
    if preset.get("builtin"):
        raise ValueError("Built-in presets cannot be deleted")
    del entry["presets"][preset_id]


def apply_to_camera(cam, saved_values):
    """Push values to the device and verify every active write by reading it back."""
    result = RestoreResult()
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

    # Apply auto/manual switches before the values whose active state they gate.
    for pass_types in ((2, 3), (1,)):
        cam.refresh_flags()
        for ctrl_id, value in items:
            ctrl = by_id[ctrl_id]
            key = str(ctrl_id)
            if ctrl.type not in pass_types:
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
        cam.refresh_flags()
    return result


def apply_all(quiet=False, retry_seconds=0):
    """Restore saved settings to connected cameras, optionally waiting for them."""
    import v4l2ctl

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
                    aggregate.merge(result)
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
                    print(f"logioki: control {ctrl_id}: {reason}", file=os.sys.stderr)
                if not matched:
                    print("logioki: no saved camera is currently available", file=os.sys.stderr)
            return matched, aggregate
        time.sleep(min(2, max(0, deadline - time.monotonic())))
