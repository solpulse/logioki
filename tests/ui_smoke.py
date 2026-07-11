"""Construct the unified QML window with a fake camera."""

# ruff: noqa: E402 -- source/installed import selection must happen before imports.

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
source_root = Path(__file__).resolve().parents[1]
if os.environ.get("LOGIOKI_PACKAGED_SMOKE") != "1":
    sys.path.insert(0, str(source_root))

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QAccessible, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from shiboken6 import getCppPointer, wrapInstance

import application_view_model
import qml_app
import settings_repository
import store
import v4l2ctl

if os.environ.get("LOGIOKI_PACKAGED_SMOKE") == "1":
    imported_app = Path(qml_app.__file__).resolve()
    if imported_app.is_relative_to(source_root):
        raise RuntimeError(f"packaged smoke imported checkout source: {imported_app}")


class FakeCamera:
    card = "MX Brio"
    path = "/dev/video0"
    key = "usb:046d:0944:UI-SMOKE"
    identity_label = "UI-SMOKE"
    bus_info = "usb-smoke"

    def __init__(self):
        self.controls = [
            SimpleNamespace(
                id=1,
                name="Brightness",
                type=v4l2ctl.TYPE_INT,
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
                type=v4l2ctl.TYPE_BOOL,
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
                type=v4l2ctl.TYPE_MENU,
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

    def get(self, control_id):
        return self.values[control_id]

    def set(self, control_id, value):
        self.values[control_id] = value

    def refresh_flags(self):
        return None

    def close(self):
        return None


fake = FakeCamera()
settings = store._empty_data()
settings_repository.store.load = lambda: settings
settings_repository.store.save = lambda _data: None
application_view_model.QMediaDevices.videoInputs = lambda: []
application_view_model.StartupManager.restore_enabled = lambda _self: False
application_view_model.StartupManager.open_gui_enabled = lambda _self: False
startup_writes = []
application_view_model.StartupManager.set_restore_enabled = lambda _self, enabled: (
    startup_writes.append(("restore", enabled)) or (True, None)
)
application_view_model.StartupManager.set_open_gui_enabled = lambda _self, enabled: (
    startup_writes.append(("gui", enabled)) or (True, None)
)

app = QGuiApplication([])
app.setOrganizationName("Solpulse")
app.setOrganizationDomain("github.com/solpulse")
app.setApplicationName("Logioki UI Smoke")
QAccessible.setActive(True)
requested_scheme = os.environ.get("UI_SMOKE_SCHEME")
if not requested_scheme and os.environ.get("UI_SMOKE_DARK") == "1":
    requested_scheme = "dark"
if requested_scheme:
    os.environ["LOGIOKI_COLOR_SCHEME"] = requested_scheme
    scheme = Qt.ColorScheme.Dark if requested_scheme == "dark" else Qt.ColorScheme.Light
    app.styleHints().setColorScheme(scheme)
engine = QQmlApplicationEngine()
qml_dir = qml_app._resource_dir()
engine.addImportPath(str(qml_dir.parent))
model = application_view_model.ApplicationViewModel(discover=lambda: [fake])
engine.setInitialProperties({"vm": model})
engine.load(QUrl.fromLocalFile(str(qml_dir / "Main.qml")))
if not engine.rootObjects():
    raise RuntimeError("QML window did not construct")
requested_width = int(os.environ.get("UI_SMOKE_WIDTH", "1180"))
engine.rootObjects()[0].setWidth(requested_width)

attempts = 0
accessibility_stage = 0
accessibility_stage_attempt = 0
dynamic_accessible_names = {}
dynamic_geometry = {}
keyboard_focus_received = False
keyboard_tab_advanced = False
keyboard_focus_before = None
menu_value_synchronized = False
preview_pointer = None
preview_survived_resize = False
breakpoint_switched = False


def accessible_name(root, object_name):
    items = list(root.findChildren(QObject, object_name))
    stack = [wrapInstance(getCppPointer(root)[0], QQuickWindow).contentItem()]
    while stack:
        item = stack.pop()
        if item.objectName() == object_name and item not in items:
            items.append(item)
        stack.extend(item.childItems())
    for item in items:
        interface = QAccessible.queryAccessibleInterface(item)
        if interface is not None:
            name = interface.text(QAccessible.Text.Name)
            if name:
                return name
    return ""


def visual_items(root, object_name):
    matches = []
    stack = [wrapInstance(getCppPointer(root)[0], QQuickWindow).contentItem()]
    while stack:
        item = stack.pop()
        if item.objectName() == object_name:
            matches.append(item)
        stack.extend(item.childItems())
    return matches


def visual_item(root, object_name):
    matches = visual_items(root, object_name)
    return matches[0] if matches else None


def verify_window():
    global accessibility_stage, accessibility_stage_attempt, attempts
    global keyboard_focus_received, keyboard_tab_advanced, keyboard_focus_before
    global menu_value_synchronized, preview_pointer, preview_survived_resize
    global breakpoint_switched
    attempts += 1
    root = engine.rootObjects()[0]
    ready = not model.busy and model.hasCamera
    if not ready and attempts < 100:
        return
    navigation = root.findChild(QObject, "inspectorNavigation")
    inspector_stack = root.findChild(QObject, "inspectorStack")
    wide_layout = root.findChild(QObject, "wideLayout")
    stacked_layout = root.findChild(QObject, "stackedLayout")
    if accessibility_stage == 0:
        navigation.setProperty("currentIndex", 1)
        accessibility_stage = 1
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 1:
        if attempts - accessibility_stage_attempt < 3:
            return
        dynamic_accessible_names["control-1"] = accessible_name(root, "control-1")
        for object_name in ("control-wrapper-1", "camera-control-row-1", "control-1"):
            item = visual_item(root, object_name)
            dynamic_geometry[object_name] = (
                (
                    item.property("visible"),
                    item.property("x"),
                    item.property("y"),
                    item.property("width"),
                    item.property("height"),
                )
                if item is not None
                else None
            )
        repeater = root.findChild(QObject, "controlsRepeater-image")
        dynamic_geometry["image-count"] = repeater.property("count") if repeater else None
        focus_item = visual_item(root, "control-1")
        if focus_item is not None:
            focus_item.forceActiveFocus(Qt.FocusReason.TabFocusReason)
            keyboard_focus_received = focus_item.hasActiveFocus()
            keyboard_focus_before = app.focusObject()
            QTest.keyClick(root, Qt.Key.Key_Tab)
        accessibility_stage = 11
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 11:
        if attempts - accessibility_stage_attempt < 3:
            return
        keyboard_tab_advanced = (
            app.focusObject() is not None and app.focusObject() is not keyboard_focus_before
        )
        navigation.setProperty("currentIndex", 2)
        accessibility_stage = 2
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 2:
        if attempts - accessibility_stage_attempt < 3:
            return
        for object_name in ("control-2", "control-3"):
            dynamic_accessible_names[object_name] = accessible_name(root, object_name)
            item = visual_item(root, object_name)
            dynamic_geometry[object_name] = (
                (
                    item.property("visible"),
                    item.property("x"),
                    item.property("y"),
                    item.property("width"),
                    item.property("height"),
                )
                if item is not None
                else None
            )
        repeater = root.findChild(QObject, "controlsRepeater-camera")
        dynamic_geometry["camera-count"] = repeater.property("count") if repeater else None
        model.setControl("3", 2, True)
        accessibility_stage = 21
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 21:
        if model.busy or attempts - accessibility_stage_attempt < 3:
            return
        menu_item = visual_item(root, "control-3")
        menu_value_synchronized = menu_item is not None and menu_item.property("hardwareValue") == 2
        final_tab = int(os.environ.get("UI_SMOKE_TAB", "0"))
        navigation.setProperty("currentIndex", final_tab)
        accessibility_stage = 3
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 3:
        if attempts - accessibility_stage_attempt < 3:
            return
        preview = visual_item(root, "previewOutput")
        preview_pointer = getCppPointer(preview)[0] if preview is not None else None
        root.setWidth(900 if requested_width >= 1024 else 1180)
        accessibility_stage = 31
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 31:
        if attempts - accessibility_stage_attempt < 3:
            return
        preview = visual_item(root, "previewOutput")
        breakpoint_switched = (
            stacked_layout.property("visible") and not wide_layout.property("visible")
            if requested_width >= 1024
            else wide_layout.property("visible") and not stacked_layout.property("visible")
        )
        preview_survived_resize = (
            preview is not None and getCppPointer(preview)[0] == preview_pointer
        )
        root.setWidth(requested_width)
        accessibility_stage = 32
        accessibility_stage_attempt = attempts
        return
    if accessibility_stage == 32:
        if attempts - accessibility_stage_attempt < 3:
            return
        preview = visual_item(root, "previewOutput")
        preview_survived_resize = (
            preview_survived_resize
            and preview is not None
            and getCppPointer(preview)[0] == preview_pointer
        )
        accessibility_stage = 4

    accessible_names = []
    for object_name in (
        "previewOutput",
        "restoreStartupSwitch",
        "openStartupSwitch",
    ):
        accessible_names.append(accessible_name(root, object_name))
    responsive = (
        wide_layout.property("visible") and not stacked_layout.property("visible")
        if requested_width >= 1024
        else stacked_layout.property("visible") and not wide_layout.property("visible")
    )
    preview_output_count = len(visual_items(root, "previewOutput"))
    expected_high_contrast = os.environ.get("LOGIOKI_HIGH_CONTRAST", "").casefold() in {
        "1",
        "true",
        "yes",
    }
    expected_reduced_motion = os.environ.get("LOGIOKI_REDUCED_MOTION", "").casefold() in {
        "1",
        "true",
        "yes",
    }
    theme_verified = (
        root.property("highContrastMode") == expected_high_contrast
        and root.property("reducedMotionMode") == expected_reduced_motion
        and root.property("effectiveTransitionDuration") == (0 if expected_reduced_motion else 160)
        and root.property("effectivePlatformProfile") == model.platformProfile
        and root.property("darkMode")
    )
    verified = (
        ready
        and navigation is not None
        and responsive
        and theme_verified
        and keyboard_focus_received
        and keyboard_tab_advanced
        and menu_value_synchronized
        and breakpoint_switched
        and preview_survived_resize
        and preview_output_count == 1
        and not startup_writes
        and accessible_names
        == [
            "Live camera preview",
            "Restore settings at login",
            "Open Logioki at login",
        ]
        and dynamic_accessible_names
        == {
            "control-1": "Brightness",
            "control-2": "Auto Focus",
            "control-3": "Power Line Frequency",
        }
        and model.cameraModel.rowCount() == 1
        and model.controlModel.rowCount() == 3
        and dynamic_geometry.get("image-count") == 1
        and dynamic_geometry.get("camera-count") == 2
        and model.presetModel.rowCount() == 3
        and model.cameraName == "MX Brio"
        and model.platformProfile == os.environ.get("LOGIOKI_DESKTOP_STYLE", model.platformProfile)
    )
    if not verified or os.environ.get("UI_SMOKE_DEBUG") == "1":
        control_geometry = {
            name: [
                (item.metaObject().className(), item.property("x"), item.property("width"))
                for item in [visual_item(root, name)]
                if item is not None
            ]
            for name in ("control-1", "control-2", "control-3")
        }
        final_dynamic_geometry = {
            name: (
                visual_item(root, name).property("visible"),
                visual_item(root, name).property("x"),
                visual_item(root, name).property("y"),
                visual_item(root, name).property("width"),
                visual_item(root, name).property("height"),
            )
            if visual_item(root, name) is not None
            else None
            for name in (
                "control-wrapper-1",
                "camera-control-row-1",
                "control-1",
                "control-exact-1",
            )
        }
        control_rows = [
            (
                item.objectName(),
                item.property("title"),
                item.property("visible"),
                item.property("width"),
                item.property("height"),
            )
            for item in root.findChildren(QObject)
            if "ControlRow" in item.metaObject().className()
        ]
        page_geometry = {}
        for name in (
            "controlsPage-image",
            "controlsColumn-image",
            "controlsPage-camera",
            "controlsColumn-camera",
        ):
            item = root.findChild(QObject, name)
            page_geometry[name] = {
                key: item.property(key)
                for key in ("visible", "width", "height", "availableWidth", "contentWidth")
                if item is not None
            }
        print(
            {
                "ready": ready,
                "navigation": navigation is not None,
                "navigation_index": navigation.property("currentIndex"),
                "stack_index": inspector_stack.property("currentIndex"),
                "responsive": responsive,
                "theme_verified": theme_verified,
                "keyboard_focus_received": keyboard_focus_received,
                "keyboard_tab_advanced": keyboard_tab_advanced,
                "menu_value_synchronized": menu_value_synchronized,
                "breakpoint_switched": breakpoint_switched,
                "preview_survived_resize": preview_survived_resize,
                "preview_output_count": preview_output_count,
                "menu_state": (
                    {
                        "currentIndex": visual_item(root, "control-3").property("currentIndex"),
                        "hardwareValue": visual_item(root, "control-3").property("hardwareValue"),
                        "count": visual_item(root, "control-3").property("count"),
                        "modelValue": model.controlModel._items[2].value,
                    }
                    if visual_item(root, "control-3") is not None
                    else None
                ),
                "width": root.width(),
                "wide_visible": wide_layout.property("visible"),
                "stacked_visible": stacked_layout.property("visible"),
                "startup_writes": startup_writes,
                "accessible_names": accessible_names,
                "dynamic_accessible_names": dynamic_accessible_names,
                "control_geometry": control_geometry,
                "dynamic_geometry": dynamic_geometry,
                "final_dynamic_geometry": final_dynamic_geometry,
                "control_rows": control_rows,
                "page_geometry": page_geometry,
                "cameras": model.cameraModel.rowCount(),
                "controls": model.controlModel.rowCount(),
                "presets": model.presetModel.rowCount(),
                "profile": model.platformProfile,
            },
            file=sys.stderr,
        )
    screenshot = os.environ.get("UI_SMOKE_SCREENSHOT")
    if screenshot:
        app.primaryScreen().grabWindow(root.winId()).save(screenshot)
    timer.stop()
    root.close()
    model.shutdown()
    engine.deleteLater()
    QTimer.singleShot(0, lambda: app.exit(0 if verified else 1))


timer = QTimer()
timer.setInterval(20)
timer.timeout.connect(verify_window)
timer.start()
raise SystemExit(app.exec())
