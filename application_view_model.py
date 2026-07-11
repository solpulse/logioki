"""Qt/QML application boundary for camera state and commands."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QFileSystemWatcher,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoFrameFormat

import diagnostics
import v4l2ctl
from camera_backend import CameraBackend
from desktop import detect_desktop
from firmware_provider import FirmwareProvider, FirmwareState
from models import CameraListItem, ControlListItem, ErrorListItem, PresetListItem
from settings_repository import SettingsRepository
from startup_manager import StartupManager

LOGGER = logging.getLogger(__name__)


def intent_group(name: str, backend_group: str) -> str:
    lowered = name.casefold()
    if any(word in lowered for word in ("exposure", "gain", "backlight")):
        return "Exposure"
    if "white balance" in lowered or "temperature" in lowered:
        return "White Balance"
    if "focus" in lowered:
        return "Focus"
    if any(word in lowered for word in ("zoom", "pan", "tilt", "framing")):
        return "Framing"
    if any(word in lowered for word in ("power line", "frequency")):
        return "Device Behavior"
    image_words = ("brightness", "contrast", "saturation", "sharpness", "hue", "gamma")
    if any(word in lowered for word in image_words):
        return "Image"
    return backend_group.removesuffix(" Controls") or "Image"


class ObjectListModel(QAbstractListModel):
    """Read-only typed records; backend dictionaries never cross into QML."""

    def __init__(self, roles: tuple[str, ...], parent=None):
        super().__init__(parent)
        self._roles = roles
        self._items: list[object] = []

    def roleNames(self):
        return {
            Qt.ItemDataRole.UserRole + index: QByteArray(name.encode())
            for index, name in enumerate(self._roles)
        }

    def rowCount(self, parent=None):
        parent = parent or QModelIndex()
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        offset = int(role) - int(Qt.ItemDataRole.UserRole)
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        if not 0 <= offset < len(self._roles):
            return None
        return getattr(self._items[index.row()], self._roles[offset])

    def replace(self, records) -> None:
        self.beginResetModel()
        self._items = list(records)
        self.endResetModel()

    def item(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None


def camera_labels(cameras) -> list[str]:
    counts: dict[str, int] = {}
    for camera in cameras:
        counts[camera.card] = counts.get(camera.card, 0) + 1
    return [
        f"{camera.card} — {camera.identity_label}" if counts[camera.card] > 1 else camera.card
        for camera in cameras
    ]


def _is_compressed_preview_format(camera_format) -> bool:
    return (
        getattr(camera_format, "pixelFormat", lambda: None)()
        == QVideoFrameFormat.PixelFormat.Format_Jpeg
    )


def available_preview_formats(formats):
    """Return one efficient format for each resolution/frame-rate mode."""
    modes = {}
    for camera_format in formats:
        size = camera_format.resolution()
        key = (size.width(), size.height(), round(float(camera_format.maxFrameRate()), 2))
        current = modes.get(key)
        if current is None or (
            _is_compressed_preview_format(camera_format)
            and not _is_compressed_preview_format(current)
        ):
            modes[key] = camera_format
    return sorted(
        modes.values(),
        key=lambda camera_format: (
            camera_format.resolution().width() * camera_format.resolution().height(),
            float(camera_format.maxFrameRate()),
        ),
        reverse=True,
    )


def preview_format_label(camera_format) -> str:
    size = camera_format.resolution()
    codec = "MJPEG" if _is_compressed_preview_format(camera_format) else "Native"
    return f"{size.width()}×{size.height()} · {camera_format.maxFrameRate():g} fps · {codec}"


def select_preview_format(formats):
    """Prefer smooth 1080p60, while retaining higher modes for selection."""
    if not formats:
        return None

    def rank(camera_format):
        size = camera_format.resolution()
        fps = float(camera_format.maxFrameRate())
        smooth_full_hd = size.width() == 1920 and size.height() == 1080 and 59.0 <= fps <= 61.0
        return (
            smooth_full_hd,
            _is_compressed_preview_format(camera_format),
            size.width() * size.height() * min(fps, 60.0),
            size.width() * size.height(),
            fps,
        )

    return max(available_preview_formats(formats), key=rank)


def find_preview_device(devices, path: str):
    """Return only a Qt device whose opaque identifier exactly matches the node."""
    path_bytes = path.encode()
    return next((item for item in devices if bytes(item.id()) == path_bytes), None)


def writable_values(camera, live_values: dict[str, int]) -> dict[str, int]:
    writable_ids = {str(control.id) for control in camera.controls if not control.read_only}
    return {key: value for key, value in live_values.items() if key in writable_ids}


class PreviewController(QObject):
    stateChanged = Signal()
    modesChanged = Signal()
    errorReported = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session = QMediaCaptureSession(self)
        self._camera = None
        self._state = "Preview unavailable"
        self._format = "No active preview"
        self._generation = 0
        self._visible = True
        self._formats = []
        self._format_options = []
        self._current_format_index = -1

    @Property(QObject, constant=True)
    def captureSession(self):
        return self._session

    @Slot(QObject)
    def setVideoOutput(self, output):
        self._session.setVideoOutput(output)

    @Property(str, notify=stateChanged)
    def state(self):
        return self._state

    @Property(str, notify=stateChanged)
    def format(self):
        return self._format

    @Property("QStringList", notify=modesChanged)
    def formatOptions(self):
        return self._format_options

    @Property(int, notify=modesChanged)
    def currentFormatIndex(self):
        return self._current_format_index

    def start(self, path: str) -> None:
        self.stop()
        self._generation += 1
        generation = self._generation
        device = find_preview_device(QMediaDevices.videoInputs(), path)
        if device is None:
            self._set_state("Preview unavailable", "Qt Multimedia did not expose this exact device")
            return
        camera = QCamera(device, self)
        camera.errorOccurred.connect(lambda _error, message, g=generation: self._error(g, message))
        self._formats = available_preview_formats(device.videoFormats())
        self._format_options = [preview_format_label(item) for item in self._formats]
        camera_format = select_preview_format(self._formats)
        if camera_format is not None:
            camera.setCameraFormat(camera_format)
            self._current_format_index = self._formats.index(camera_format)
            self._format = preview_format_label(camera_format)
        self.modesChanged.emit()
        self._camera = camera
        self._session.setCamera(camera)
        if self._visible:
            camera.start()
        self._set_state("Connected", self._format)

    def _error(self, generation: int, message: str) -> None:
        if generation == self._generation:
            state = "Busy" if "busy" in (message or "").casefold() else "Preview unavailable"
            detail = message or "The preview stream is unavailable"
            self._set_state(state, detail)
            self.errorReported.emit(detail)

    def stop(self) -> None:
        self._generation += 1
        camera, self._camera = self._camera, None
        self._session.setCamera(None)
        if camera is not None:
            camera.stop()
            camera.deleteLater()
        self._formats = []
        self._format_options = []
        self._current_format_index = -1
        self.modesChanged.emit()
        self._set_state("Preview unavailable", "No active preview")

    @Slot(int)
    def selectFormat(self, index: int) -> None:
        if self._camera is None or not 0 <= index < len(self._formats):
            return
        if index == self._current_format_index:
            return
        camera_format = self._formats[index]
        self._camera.stop()
        self._camera.setCameraFormat(camera_format)
        self._current_format_index = index
        self._format = preview_format_label(camera_format)
        if self._visible:
            self._camera.start()
        self.modesChanged.emit()
        self._set_state("Connected", self._format)

    @Slot(bool)
    def setVisible(self, visible: bool) -> None:
        self._visible = visible
        if self._camera is not None:
            self._camera.start() if visible else self._camera.stop()

    def _set_state(self, state: str, camera_format: str) -> None:
        self._state, self._format = state, camera_format
        self.stateChanged.emit()


class ApplicationViewModel(QObject):
    changed = Signal()
    notification = Signal(str, str)
    taskComplete = Signal(object)

    def __init__(
        self,
        parent=None,
        discover=None,
        settings_repository=None,
        firmware_provider=None,
        startup_manager=None,
    ):
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="logioki-camera")
        self._pending_tasks = {}
        self._pending_control_write = None
        self._control_writes_active = 0
        self._closed = False
        self._settings_repository = settings_repository or SettingsRepository()
        self._settings = self._settings_repository.empty()
        self._startup = startup_manager or StartupManager()
        self._firmware = firmware_provider or FirmwareProvider()
        self._firmware_state = FirmwareState(
            available=False,
            version="Unavailable",
            status="Connect a camera to check firmware support.",
        )
        self._camera_backend = CameraBackend(discover)
        self._discover = self._camera_backend.discover
        self._registry = self._camera_backend.registry()
        self._cameras = []
        self._camera = None
        self._entry = None
        self._live_values = {}
        self._selected_camera = -1
        self._connection = "No camera"
        self._busy_tasks = 0
        self._dirty = False
        self._restore_at_login = False
        self._open_at_login = False
        self._active_preset = "Unsaved"
        self._restore_summary = "No restore has run in this session"
        self._recent_errors: list[str] = []
        self.cameraModel = ObjectListModel(("label", "key"), self)
        control_roles = (
            "controlId",
            "name",
            "kind",
            "group",
            "showGroup",
            "value",
            "minimum",
            "maximum",
            "step",
            "available",
            "reason",
            "menuItems",
        )
        self.controlModel = ObjectListModel(control_roles, self)
        self.imageControlModel = ObjectListModel(control_roles, self)
        self.cameraControlModel = ObjectListModel(control_roles, self)
        self.presetModel = ObjectListModel(("presetId", "name", "builtin", "editable"), self)
        self.errorModel = ObjectListModel(("message",), self)
        self.preview = PreviewController(self)
        self.preview.stateChanged.connect(self.changed)
        self.preview.errorReported.connect(self._remember_error)
        self.taskComplete.connect(self._finish_task)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._save_async)
        self._control_timer = QTimer(self)
        self._control_timer.setSingleShot(True)
        self._control_timer.setInterval(75)
        self._control_timer.timeout.connect(self._drain_control_write)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self.refreshDevices)
        self._watcher = QFileSystemWatcher(["/dev"], self)
        self._watcher.directoryChanged.connect(lambda _path: self._refresh_timer.start())
        self._submit(self._bootstrap, self._bootstrapped)

    def _bootstrap(self):
        settings = self._settings_repository.load()
        app_settings = settings.get("app", {})
        self._startup.load_state(
            app_settings.get("auto_restore", False),
            app_settings.get("open_at_login", False),
        )
        return (
            settings,
            self._discover(),
            self._startup.restore_enabled(),
            self._startup.open_gui_enabled(),
        )

    def _bootstrapped(self, result):
        settings, cameras, restore_enabled, open_enabled = result
        self._settings = settings
        self._registry = self._camera_backend.registry(cameras)
        self._cameras = list(self._registry.devices)
        self._restore_at_login = restore_enabled
        self._open_at_login = open_enabled
        self._settings["app"]["auto_restore"] = restore_enabled
        self._settings["app"]["open_at_login"] = open_enabled
        self._update_camera_model()
        if self._cameras:
            self.selectCamera(0)

    def _submit(self, operation, callback, busy=True, error_callback=None):
        if self._closed:
            return
        if busy:
            self._busy_tasks += 1
            self.changed.emit()
        future = self._executor.submit(operation)
        self._pending_tasks[future] = (callback, busy, error_callback)
        future.add_done_callback(self.taskComplete.emit)

    @Slot(object)
    def _finish_task(self, future):
        task = self._pending_tasks.pop(future, None)
        if task is None:
            return
        callback, busy, error_callback = task
        if busy:
            self._busy_tasks = max(0, self._busy_tasks - 1)
        try:
            result = future.result()
        except Exception as exc:
            if error_callback is not None:
                error_callback(exc)
            LOGGER.exception("Background operation failed")
            self._error(str(exc))
        else:
            try:
                callback(result)
            except Exception as exc:
                LOGGER.exception("Background completion callback failed")
                self._error(str(exc))
        self.changed.emit()

    @Property(QObject, constant=True)
    def cameras(self):
        return self.cameraModel

    @Property(QObject, constant=True)
    def controls(self):
        return self.controlModel

    @Property(QObject, constant=True)
    def imageControls(self):
        return self.imageControlModel

    @Property(QObject, constant=True)
    def cameraControls(self):
        return self.cameraControlModel

    @Property(QObject, constant=True)
    def presets(self):
        return self.presetModel

    @Property(QObject, constant=True)
    def errors(self):
        return self.errorModel

    @Property(QObject, constant=True)
    def previewController(self):
        return self.preview

    @Property(str, constant=True)
    def platformProfile(self):
        return detect_desktop()

    @Property(bool, constant=True)
    def highContrast(self):
        return os.environ.get("LOGIOKI_HIGH_CONTRAST", "").casefold() in {"1", "true", "yes"}

    @Property(bool, constant=True)
    def reducedMotion(self):
        return os.environ.get("LOGIOKI_REDUCED_MOTION", "").casefold() in {"1", "true", "yes"}

    @Property(int, constant=True)
    def colorSchemeOverride(self):
        scheme = os.environ.get("LOGIOKI_COLOR_SCHEME", "").casefold()
        return 1 if scheme == "dark" else 0 if scheme == "light" else -1

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy_tasks > 0

    @Property(int, notify=changed)
    def selectedCamera(self):
        return self._selected_camera

    @Property(str, notify=changed)
    def cameraName(self):
        return self._camera.card if self._camera else "No camera"

    @Property(str, notify=changed)
    def connectionState(self):
        if self._camera is not None and self.preview.state != "Connected":
            return self.preview.state
        return self._connection

    @Property(str, notify=changed)
    def activePreset(self):
        return (
            f"{self._active_preset} — Modified"
            if self._dirty and self._active_preset != "Unsaved"
            else self._active_preset
        )

    @Property(bool, notify=changed)
    def hasCamera(self):
        return self._camera is not None

    @Property(bool, notify=changed)
    def restoreAtLogin(self):
        return self._restore_at_login

    @Property(bool, notify=changed)
    def openAtLogin(self):
        return self._open_at_login

    def _update_camera_model(self):
        self.cameraModel.replace(
            CameraListItem(label, camera.key)
            for label, camera in zip(camera_labels(self._cameras), self._cameras, strict=True)
        )

    @Slot(int)
    def selectCamera(self, index: int):
        if self.busy or not 0 <= index < len(self._cameras):
            return
        self.preview.stop()
        self._selected_camera = index
        camera = self._cameras[index]
        self._connection = "Reconnecting"
        self.changed.emit()

        def operation():
            known_camera = camera.key in self._settings.get("cameras", {})
            known_legacy = camera.card in self._settings.get("legacy_cameras", {})
            entry = self._settings_repository.camera_entry(self._settings, camera)
            result = (
                self._settings_repository.apply(camera, entry.get("controls", {}))
                if (known_camera or known_legacy) and entry.get("controls")
                else self._settings_repository.empty_restore_result()
            )
            live_values = self._settings_repository.capture(camera, include_read_only=True)
            return (
                camera,
                entry,
                result,
                writable_values(camera, live_values),
                live_values,
                self._firmware.state_for(camera),
            )

        self._submit(operation, self._camera_selected)

    def _camera_selected(self, result):
        camera, entry, restore, persisted_values, live_values, firmware_state = result
        if (
            self._selected_camera >= len(self._cameras)
            or self._cameras[self._selected_camera].key != camera.key
        ):
            return
        self._camera, self._entry = camera, entry
        entry["controls"] = persisted_values
        self._live_values = live_values
        self._firmware_state = firmware_state
        self._connection = "Connected"
        self._active_preset = (
            entry.get("presets", {})
            .get(entry.get("selected_preset", ""), {})
            .get("name", "Unsaved")
        )
        self._dirty = not self._matches_selected_preset()
        if self._closed:
            return
        self._rebuild_models()
        self.preview.start(camera.path)
        self._report_result("Restored settings", restore)
        self._save_async()

    def _matches_selected_preset(self):
        if not self._entry:
            return False
        selected = self._entry.get("selected_preset")
        preset = self._entry.get("presets", {}).get(selected)
        return bool(preset) and preset.get("controls") == self._entry.get("controls")

    def _rebuild_models(self):
        if not self._camera or not self._entry:
            self.controlModel.replace([])
            self.imageControlModel.replace([])
            self.cameraControlModel.replace([])
            self.presetModel.replace([])
            return
        values = self._live_values
        descriptors = []
        for group, controls in self._camera.groups.items():
            for control in controls:
                descriptors.append((intent_group(control.name, group), control))
        group_order = {
            name: index
            for index, name in enumerate(
                ("Image", "Exposure", "White Balance", "Focus", "Framing", "Device Behavior")
            )
        }
        descriptors.sort(key=lambda item: group_order.get(item[0], len(group_order)))
        records = []
        shown_groups = set()
        for intent, control in descriptors:
            kind = (
                "toggle"
                if control.type == v4l2ctl.TYPE_BOOL
                else "menu"
                if control.type == v4l2ctl.TYPE_MENU
                else "number"
            )
            enabled = not control.inactive and not control.read_only
            reason = (
                "Read-only on this camera"
                if control.read_only
                else "Available when its automatic mode is off"
                if control.inactive
                else ""
            )
            menu = [{"value": value, "label": label} for value, label in control.menu_items]
            records.append(
                ControlListItem(
                    controlId=str(control.id),
                    name=control.name,
                    kind=kind,
                    group=intent,
                    showGroup=intent not in shown_groups,
                    value=values.get(str(control.id), control.default),
                    minimum=control.minimum,
                    maximum=control.maximum,
                    step=control.step,
                    available=enabled,
                    reason=reason,
                    menuItems=menu,
                )
            )
            shown_groups.add(intent)
        self.controlModel.replace(records)
        image_groups = {"Image", "White Balance"}
        self.imageControlModel.replace(item for item in records if item.group in image_groups)
        self.cameraControlModel.replace(item for item in records if item.group not in image_groups)
        self.presetModel.replace(
            PresetListItem(
                presetId=pid,
                name=name,
                builtin=self._entry["presets"][pid].get("builtin", False),
                editable=pid != "default",
            )
            for pid, name in self._settings_repository.preset_items(self._entry)
        )

    @Slot(str, int, bool)
    def setControl(self, control_id: str, value: int, final: bool = True):
        if not self._camera or (self.busy and not self._control_writes_active):
            return
        camera, entry = self._camera, self._entry
        control = next((c for c in camera.controls if str(c.id) == control_id), None)
        if control is None:
            return
        self._pending_control_write = (camera, entry, control, int(value))
        if final:
            self._control_timer.stop()
            self._drain_control_write()
        else:
            self._control_timer.start()

    @Slot()
    def _drain_control_write(self, force=False):
        if self._pending_control_write is None or (self._control_writes_active and not force):
            return
        camera, entry, control, value = self._pending_control_write
        self._pending_control_write = None
        if camera is not self._camera or entry is not self._entry:
            return
        self._control_writes_active += 1
        self._submit(
            lambda: self._perform_control_write(camera, control, value),
            lambda result: self._control_set(entry, result),
            error_callback=self._control_write_failed,
        )

    def _perform_control_write(self, camera, control, value):
        error = None
        try:
            camera.set(control.id, value)
        except (OSError, OverflowError, TypeError) as exc:
            error = getattr(exc, "strerror", None) or str(exc)
        actual = camera.get(control.id)
        camera.refresh_flags()
        live_values = self._settings_repository.capture(camera, include_read_only=True)
        return (
            control,
            value,
            actual,
            writable_values(camera, live_values),
            live_values,
            error,
        )

    def _control_set(self, entry, result):
        self._control_writes_active -= 1
        control, requested, actual, values, live_values, error = result
        if entry is not self._entry:
            self._continue_control_writes()
            return
        entry["controls"] = values
        self._live_values = live_values
        self._dirty = not self._matches_selected_preset()
        if self._closed:
            return
        if error:
            detail = f"{control.name} remains {actual}: {error}"
            self._remember_error(detail)
            self.notification.emit(
                "Camera rejected the change",
                detail,
            )
        elif actual != requested:
            self.notification.emit(
                "Camera adjusted the value",
                f"{control.name} is {actual}; the camera did not accept {requested}.",
            )
        self._rebuild_models()
        self._save_timer.start()
        self._continue_control_writes()

    def _control_write_failed(self, _error):
        self._control_writes_active -= 1
        self._continue_control_writes()

    def _continue_control_writes(self):
        if not self._closed and self._pending_control_write is not None:
            QTimer.singleShot(0, self._drain_control_write)

    @Slot(int)
    def applyPreset(self, index: int):
        item = self.presetModel.item(index)
        if not item or self.busy or not self._camera:
            return
        preset_id = item.presetId
        preset = self._entry["presets"][preset_id]

        def operation():
            restore = self._settings_repository.apply(self._camera, preset["controls"])
            live_values = self._settings_repository.capture(self._camera, include_read_only=True)
            return restore, writable_values(self._camera, live_values), live_values

        self._submit(
            operation,
            lambda result: self._preset_applied(preset_id, preset["name"], result),
        )

    def _preset_applied(self, preset_id, name, result):
        restore, values, live_values = result
        self._entry["controls"] = values
        self._live_values = live_values
        self._entry["selected_preset"] = preset_id
        self._active_preset = name
        self._dirty = values != self._entry["presets"][preset_id]["controls"]
        if self._closed:
            return
        self._rebuild_models()
        self._save_async()
        self._report_result(f"Applied {name}", restore)

    @Slot()
    def resetDefaults(self):
        if not self._entry:
            return
        index = next(
            (i for i, item in enumerate(self.presetModel._items) if item.presetId == "default"),
            -1,
        )
        self.applyPreset(index)

    @Slot(str)
    def createPreset(self, name: str):
        if not self._entry or not name.strip():
            return
        try:
            preset_id = self._settings_repository.create_preset(
                self._entry, name, self._entry["controls"]
            )
        except ValueError as exc:
            self._error(str(exc))
            return
        self._entry["selected_preset"] = preset_id
        self._active_preset = self._entry["presets"][preset_id]["name"]
        self._dirty = False
        self._rebuild_models()
        self._save_async()

    @Slot(int)
    def deletePreset(self, index: int):
        item = self.presetModel.item(index)
        if not item:
            return
        try:
            self._settings_repository.delete_preset(self._entry, item.presetId)
        except (KeyError, ValueError) as exc:
            self._error(str(exc))
            return
        if self._entry.get("selected_preset") == item.presetId:
            self._entry["selected_preset"] = ""
            self._active_preset = "Unsaved"
            self._dirty = False
        self._rebuild_models()
        self._save_async()

    @Slot(int)
    def updatePreset(self, index: int):
        item = self.presetModel.item(index)
        if not item or not item.editable or not self._entry:
            return
        try:
            self._settings_repository.update_preset(
                self._entry, item.presetId, self._entry["controls"]
            )
        except (KeyError, ValueError) as exc:
            self._error(str(exc))
            return
        self._entry["selected_preset"] = item.presetId
        self._active_preset = item.name
        self._dirty = False
        self._rebuild_models()
        self._save_async()

    @Property(str, notify=changed)
    def diagnosticsText(self):
        if not self._camera:
            return "Connect a camera to view diagnostics."
        report = diagnostics.camera_report(
            self._camera,
            {"state": self.preview.state, "format": self.preview.format},
            self._recent_errors,
            {
                "available": self._firmware_state.available,
                "version": self._firmware_state.version,
                "status": self._firmware_state.status,
            },
            self._live_values,
        )
        camera = report["camera"]
        supported = (
            ", ".join(
                f"{item['name']}={item['current']}" if item["current"] is not None else item["name"]
                for item in report["supported_controls"]
            )
            or "None"
        )
        unsupported = (
            ", ".join(
                f"{item['name']} ({item['reason']})" for item in report["unsupported_controls"]
            )
            or "None reported"
        )
        recent_errors = "; ".join(report["recent_errors"]) or "None"
        return "\n".join(
            (
                f"Model: {camera['model']}",
                f"Identity: {camera['identity']}",
                f"USB ID: {camera['usb_id']}",
                f"Driver path: {camera['driver_path']}",
                f"Driver: {camera['driver']}",
                f"Bus: {camera['bus']}",
                f"Firmware: {camera['firmware']}",
                f"Preview: {self.preview.state} · {self.preview.format}",
                f"Supported controls: {supported}",
                f"Unsupported controls: {unsupported}",
                f"Last restore: {self._restore_summary}",
                f"Recent errors: {recent_errors}",
            )
        )

    @Property(str, notify=changed)
    def firmwareText(self):
        return f"{self._firmware_state.status}\nVersion: {self._firmware_state.version}"

    @Property(bool, notify=changed)
    def firmwareAvailable(self):
        return self._firmware_state.available

    @Property(str, notify=changed)
    def firmwareVersion(self):
        return self._firmware_state.version

    @Property(str, notify=changed)
    def firmwareStatus(self):
        return self._firmware_state.status

    @Slot(bool)
    def setRestoreAtLogin(self, enabled):
        self._submit(
            lambda: self._startup.set_restore_enabled(enabled),
            lambda result: self._startup_finished("Restore settings at login", enabled, result),
        )

    @Slot(bool)
    def setOpenAtLogin(self, enabled):
        self._submit(
            lambda: self._startup.set_open_gui_enabled(enabled),
            lambda result: self._startup_finished("Open Logioki at login", enabled, result),
        )

    def _startup_finished(self, label, enabled, result):
        ok, error = result
        if not ok:
            self._error(f"{label}: {error or 'operation failed'}")
        else:
            if label.startswith("Restore"):
                self._restore_at_login = enabled
                self._settings["app"]["auto_restore"] = enabled
            else:
                self._open_at_login = enabled
                self._settings["app"]["open_at_login"] = enabled
            self._save_async()
            self.notification.emit("Startup updated", f"{label} is {'on' if enabled else 'off'}.")

    @Slot()
    def refreshDevices(self):
        if self.busy:
            self._refresh_timer.start()
            return
        selected_key = self._camera.key if self._camera else None
        self._submit(
            self._registry.refresh, lambda change: self._devices_refreshed(selected_key, change)
        )

    def _devices_refreshed(self, selected_key, change):
        self._cameras = list(change.devices)
        self._update_camera_model()
        keys = [c.key for c in self._cameras]
        if selected_key in keys:
            index = keys.index(selected_key)
            replacement = self._cameras[index]
            if replacement is not self._camera:
                self.preview.stop()
                self._camera = self._entry = None
                self._live_values = {}
                self._clear_firmware_state()
                self._close_removed(change.removed)
                self.selectCamera(index)
                return
            self._selected_camera = index
        elif self._cameras:
            self.preview.stop()
            self._camera = None
            self._entry = None
            self._live_values = {}
            self._clear_firmware_state()
            self._close_removed(change.removed)
            self.selectCamera(0)
            return
        else:
            self.preview.stop()
            self._camera = self._entry = None
            self._live_values = {}
            self._clear_firmware_state()
            self._selected_camera = -1
            self._connection = "No camera"
            self._rebuild_models()
        self._close_removed(change.removed)

    def _clear_firmware_state(self):
        self._firmware_state = FirmwareState(
            available=False,
            version="Unavailable",
            status="Connect a camera to check firmware support.",
        )

    def _close_removed(self, removed):
        for camera in removed:
            try:
                camera.close()
            except OSError:
                LOGGER.exception("Could not close removed camera %s", camera.path)

    @Slot(str)
    def exportDiagnostics(self, path):
        url = QUrl(path)
        if url.isLocalFile():
            path = url.toLocalFile()
        elif url.scheme():
            self._error("Diagnostics can only be exported to a local file.")
            return
        if not self._camera:
            self._error("Connect a camera before exporting diagnostics.")
            return
        report = diagnostics.camera_report(
            self._camera,
            {"state": self.preview.state, "format": self.preview.format},
            self._recent_errors,
            {
                "available": self._firmware_state.available,
                "version": self._firmware_state.version,
                "status": self._firmware_state.status,
            },
            self._live_values,
        )
        report["restore"] = self._restore_summary
        target = str(Path(path))
        self._submit(
            lambda: diagnostics.export_report(target, report),
            lambda _result: self.notification.emit("Diagnostics exported", target),
        )

    def _report_result(self, label, result):
        self._restore_summary = (
            f"{label}: {len(result.applied)} applied, "
            f"{len(result.skipped)} skipped, {len(result.failed)} failed"
        )
        if result.failed or result.skipped:
            names = {
                str(control.id): control.name
                for control in (self._camera.controls if self._camera else [])
            }
            issues = [(names.get(key, key), reason) for key, reason in result.failed.items()] + [
                (names.get(key, key), reason) for key, reason in result.skipped.items()
            ]
            details = "; ".join(f"{name}: {reason}" for name, reason in issues)
            self._remember_error(f"{label}: {details}")
            self.notification.emit(f"{label} partially completed", details)
        elif result.applied:
            self.notification.emit(label, f"{len(result.applied)} controls verified.")

    def _error(self, message):
        self._remember_error(message)
        self.notification.emit("Something went wrong", message)

    def _remember_error(self, message):
        self._recent_errors.append(message)
        del self._recent_errors[:-100]
        self.errorModel.replace(ErrorListItem(item) for item in self._recent_errors[-20:])

    def _save_async(self):
        snapshot = json.loads(json.dumps(self._settings))
        self._submit(
            lambda: self._settings_repository.save(snapshot),
            lambda _result: None,
            busy=False,
        )

    @Slot()
    def shutdown(self):
        if self._closed:
            return
        self._control_timer.stop()
        if self._pending_control_write is not None:
            self._drain_control_write(force=True)
        self._closed = True
        self.preview.stop()
        self._save_timer.stop()
        self._refresh_timer.stop()
        watched_paths = self._watcher.files()
        if watched_paths:
            self._watcher.removePaths(watched_paths)
        pending, self._pending_tasks = self._pending_tasks, {}
        for future, (callback, _busy, error_callback) in pending.items():
            try:
                result = future.result()
            except Exception as exc:
                if error_callback is not None:
                    error_callback(exc)
                LOGGER.exception("Background operation failed during shutdown")
            else:
                try:
                    callback(result)
                except Exception:
                    LOGGER.exception("Background completion callback failed during shutdown")
        self._save_timer.stop()
        snapshot = json.loads(json.dumps(self._settings))

        def finalize():
            try:
                self._settings_repository.save(snapshot)
            finally:
                self._registry.close()

        try:
            self._executor.submit(finalize).result()
        except (OSError, ValueError):
            LOGGER.exception("Could not finalize settings during shutdown")
        finally:
            self._executor.shutdown(wait=True, cancel_futures=False)
