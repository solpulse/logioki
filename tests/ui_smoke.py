"""Construct the complete GTK window with a fake camera on a virtual display."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logioki


class FakeCamera:
    card = "MX Brio"
    path = "/dev/video0"
    key = "usb:046d:0944:UI-SMOKE"
    identity_label = "UI-SMOKE"

    def __init__(self):
        self.controls = [
            SimpleNamespace(
                id=1,
                name="Brightness",
                type=logioki.v4l2ctl.TYPE_INT,
                minimum=0,
                maximum=255,
                step=1,
                default=128,
                inactive=False,
                read_only=False,
                menu_items=[],
            ),
            SimpleNamespace(
                id=2,
                name="Auto Focus",
                type=logioki.v4l2ctl.TYPE_BOOL,
                minimum=0,
                maximum=1,
                step=1,
                default=1,
                inactive=False,
                read_only=False,
                menu_items=[],
            ),
            SimpleNamespace(
                id=3,
                name="Power Line Frequency",
                type=logioki.v4l2ctl.TYPE_MENU,
                minimum=0,
                maximum=2,
                step=1,
                default=1,
                inactive=False,
                read_only=False,
                menu_items=[(0, "Disabled"), (1, "50 Hz"), (2, "60 Hz")],
            ),
        ]
        self.groups = {"User Controls": self.controls}
        self.values = {1: 128, 2: 1, 3: 1}

    def get(self, ctrl_id):
        return self.values[ctrl_id]

    def set(self, ctrl_id, value):
        self.values[ctrl_id] = value

    def refresh_flags(self):
        return None

    def close(self):
        return None


fake = FakeCamera()
logioki.v4l2ctl.list_cameras = lambda: [fake]
logioki.store.load = lambda: {"version": 2, "app": {"auto_restore": False}, "cameras": {}}
logioki.store.save = lambda _data: None
logioki.Preview.start = lambda _self, _path: None

app = logioki.App()
verified = {"ok": False}


def verify_window():
    windows = app.get_windows()
    if windows:
        window = windows[0]
        verified["ok"] = (
            hasattr(window, "preset_picker")
            and window._preset_ids[:3] == ["default", "streaming", "video-calls"]
            and hasattr(window, "save_preset_button")
            and hasattr(window, "delete_preset_button")
        )
        if os.environ.get("LOGIOKI_DESKTOP_STYLE") == "kde":
            verified["ok"] = (
                verified["ok"]
                and all(
                    window.settings_stack.get_child_by_name(name) is not None
                    for name in ("presets", "image", "camera", "startup")
                )
                and window.camera_title.get_text() == "MX Brio"
                and hasattr(window, "page_picker")
            )
    app.quit()
    return logioki.GLib.SOURCE_REMOVE


logioki.GLib.timeout_add(int(os.environ.get("UI_SMOKE_DELAY_MS", "400")), verify_window)
exit_code = app.run([])
if not verified["ok"]:
    raise RuntimeError("preset interface did not construct completely")
raise SystemExit(exit_code)
