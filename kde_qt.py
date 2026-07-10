"""Native Qt 6 frontend used on KDE Plasma when PySide6 is installed."""

from __future__ import annotations

import sys
from concurrent.futures import Future, ThreadPoolExecutor
from functools import partial
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import service
import store
import v4l2ctl
from device_monitor import DeviceRegistry

APP_ID = "io.github.solpulse.Logioki"


def application_icon() -> QIcon:
    """Resolve the installed icon, with a source-checkout fallback."""
    themed = QIcon.fromTheme(APP_ID)
    if not themed.isNull():
        return themed
    relative_icon = Path("icons/hicolor/scalable/apps") / f"{APP_ID}.svg"
    candidates = (
        Path(__file__).resolve().parent / "data" / f"{APP_ID}.svg",
        Path(sys.prefix) / "share" / relative_icon,
        Path("/usr/local/share") / relative_icon,
        Path("/usr/share") / relative_icon,
    )
    return next((QIcon(str(path)) for path in candidates if path.is_file()), QIcon())


def select_preview_format(formats, target: QSize | None = None):
    """Choose a bounded 720p format, preferring the highest available frame rate."""
    if not formats:
        return None
    target = target or QSize(1280, 720)

    def rank(camera_format):
        resolution = camera_format.resolution()
        pixels = resolution.width() * resolution.height()
        target_pixels = target.width() * target.height()
        bounded = resolution.width() <= 1920 and resolution.height() <= 1080
        exact = resolution == target
        return (
            bounded,
            exact,
            -abs(pixels - target_pixels),
            min(float(camera_format.maxFrameRate()), 60.0),
        )

    return max(formats, key=rank)


class KdeMainWindow(QMainWindow):
    """Qt-native camera controls with shared backend and persistence semantics."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Logioki")
        self.setWindowIcon(application_icon())
        self.setMinimumSize(900, 600)
        self.resize(1100, 720)
        self.settings = store.load()
        cameras = v4l2ctl.list_cameras()
        self.registry = DeviceRegistry(v4l2ctl.list_cameras, cameras)
        self.cameras = list(cameras)
        self.camera = None
        self.camera_settings = None
        self._updating = False
        self._qt_camera = None
        self._service_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="logioki-qt")
        self._service_future: Future | None = None
        self._startup_switch = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._flush_save)
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(0)
        self._rebuild_timer.timeout.connect(self._rebuild_controls)
        self._capture_session = QMediaCaptureSession(self)

        root = QWidget()
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        header.addWidget(QLabel("Camera"))
        self.device_picker = QComboBox()
        self.device_picker.currentIndexChanged.connect(self._select_index)
        header.addWidget(self.device_picker, 1)
        header.addStretch(1)
        self.reset_button = QPushButton(
            QIcon.fromTheme("edit-undo-symbolic", QIcon.fromTheme("edit-undo")),
            "Reset defaults",
        )
        self.reset_button.setToolTip("Restore every camera control to its factory default")
        self.reset_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.reset_button.clicked.connect(self._reset)
        header.addWidget(self.reset_button)
        layout.addLayout(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter = split
        split.setChildrenCollapsible(False)
        self.video = QVideoWidget()
        self.video.setMinimumSize(480, 270)
        split.addWidget(self.video)
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.controls_scroll.setMinimumWidth(380)
        split.addWidget(self.controls_scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([680, 400])
        layout.addWidget(split, 1)
        self.setCentralWidget(root)
        self._capture_session.setVideoOutput(self.video)

        self._watcher = QFileSystemWatcher(["/dev"], self)
        self._watcher.directoryChanged.connect(self._schedule_refresh)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self._refresh_devices)
        self._update_picker()
        if self.cameras:
            self._select_camera(self.cameras[0])
        else:
            self._show_empty()

    def _update_picker(self, selected_key=None) -> None:
        self._updating = True
        self.device_picker.clear()
        for camera in self.cameras:
            self.device_picker.addItem(camera.card, camera.key)
        index = self.device_picker.findData(selected_key)
        self.device_picker.setCurrentIndex(max(0, index))
        self.device_picker.setVisible(len(self.cameras) > 1)
        self._updating = False

    def _select_index(self, index: int) -> None:
        if not self._updating and 0 <= index < len(self.cameras):
            self._select_camera(self.cameras[index])

    def _select_camera(self, camera) -> None:
        self._stop_preview()
        self.camera = camera
        self.camera_settings = store.camera_entry(self.settings, camera)
        saved = self.camera_settings.get("controls", {})
        if saved:
            self._report_restore("Restored settings", store.apply_to_camera(camera, saved))
        self._build_controls()
        self._start_preview()
        self._flush_save()
        self.setWindowTitle(f"Logioki — {camera.card}")
        self.reset_button.setEnabled(True)

    def _build_controls(self) -> None:
        panel = QWidget()
        content = QVBoxLayout(panel)
        presets = QGroupBox("Image presets")
        preset_layout = QVBoxLayout(presets)
        self.preset_picker = QComboBox()
        for preset_id, name in store.preset_items(self.camera_settings):
            self.preset_picker.addItem(name, preset_id)
        selected = self.camera_settings.get("selected_preset", "streaming")
        self.preset_picker.setCurrentIndex(max(0, self.preset_picker.findData(selected)))
        self.preset_picker.currentIndexChanged.connect(self._apply_preset)
        preset_layout.addWidget(self.preset_picker)
        actions = QHBoxLayout()
        for label, callback in (
            ("New…", self._new_preset),
            ("Save", self._save_preset),
            ("Delete", self._delete_preset),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        preset_layout.addLayout(actions)
        content.addWidget(presets)

        self._updating = True
        for group_name, controls in self.camera.groups.items():
            group = QGroupBox(group_name)
            form = QFormLayout(group)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for control in controls:
                widget = self._control_widget(control)
                if widget is not None:
                    label = QLabel(control.name)
                    label.setWordWrap(True)
                    form.addRow(label, widget)
            content.addWidget(group)
        self._updating = False

        startup = QCheckBox("Apply settings at login")
        startup.setChecked(service.is_restore_service_enabled())
        startup.toggled.connect(self._toggle_autostart)
        self._startup_switch = startup
        content.addWidget(startup)
        content.addStretch()
        self.controls_scroll.setWidget(panel)

    def _control_widget(self, control):
        enabled = not control.inactive and not control.read_only
        try:
            value = self.camera.get(control.id)
        except OSError:
            return None
        if control.type == v4l2ctl.TYPE_BOOL:
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.toggled.connect(partial(self._set_control, control, mode=True))
        elif control.type == v4l2ctl.TYPE_MENU:
            widget = QComboBox()
            for menu_value, label in control.menu_items:
                widget.addItem(label, menu_value)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.currentIndexChanged.connect(
                lambda _index, c=control, w=widget: self._set_control(c, w.currentData(), True)
            )
        elif control.type == v4l2ctl.TYPE_INT:
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimumWidth(120)
            spin = QSpinBox()
            for item in (slider, spin):
                item.setRange(control.minimum, control.maximum)
                item.setSingleStep(control.step)
                item.setValue(value)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            spin.valueChanged.connect(partial(self._set_control, control))
            layout.addWidget(slider, 1)
            layout.addWidget(spin)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            return None
        widget.setEnabled(enabled)
        return widget

    def _set_control(self, control, value, mode=False) -> None:
        if self._updating:
            return
        try:
            self.camera.set(control.id, int(value))
            actual = self.camera.get(control.id)
        except OSError as exc:
            self.statusBar().showMessage(f"{control.name}: {exc}", 5000)
            return
        self.camera_settings["controls"][str(control.id)] = actual
        self._schedule_save()
        if mode:
            self.camera_settings["controls"] = store.capture_controls(self.camera)
            self._schedule_controls_rebuild()

    def _apply_preset(self, _index: int) -> None:
        if self._updating:
            return
        preset_id = self.preset_picker.currentData()
        preset = self.camera_settings["presets"].get(preset_id)
        if preset:
            result = store.apply_to_camera(self.camera, preset["controls"])
            self.camera_settings["controls"] = store.capture_controls(self.camera)
            self.camera_settings["selected_preset"] = preset_id
            self._flush_save()
            self._schedule_controls_rebuild()
            self._report_restore(f"Applied {preset['name']}", result)

    def _new_preset(self) -> None:
        name, accepted = QInputDialog.getText(self, "New preset", "Preset name")
        if accepted:
            store.create_preset(self.camera_settings, name, store.capture_controls(self.camera))
            self._flush_save()
            self._schedule_controls_rebuild()

    def _save_preset(self) -> None:
        try:
            store.update_preset(
                self.camera_settings,
                self.preset_picker.currentData(),
                store.capture_controls(self.camera),
            )
            self._flush_save()
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot save preset", str(exc))

    def _delete_preset(self) -> None:
        try:
            store.delete_preset(self.camera_settings, self.preset_picker.currentData())
            self._flush_save()
            self._schedule_controls_rebuild()
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot delete preset", str(exc))

    def _reset(self) -> None:
        result = store.apply_to_camera(
            self.camera, self.camera_settings["presets"]["default"]["controls"]
        )
        self.camera_settings["controls"] = store.capture_controls(self.camera)
        self._flush_save()
        self._schedule_controls_rebuild()
        self._report_restore("Reset to defaults", result)

    def _schedule_controls_rebuild(self) -> None:
        """Rebuild after the current native signal finishes using its sender."""
        self._rebuild_timer.start()

    def _rebuild_controls(self) -> None:
        if self.camera is not None and self.camera_settings is not None:
            self._build_controls()

    def _toggle_autostart(self, enabled: bool) -> None:
        if self._service_future is not None:
            return
        task = service.install_restore_service if enabled else service.remove_restore_service
        self._startup_switch.setEnabled(False)
        self._service_future = self._service_executor.submit(task)
        QTimer.singleShot(50, partial(self._finish_autostart, enabled))

    def _finish_autostart(self, enabled: bool) -> None:
        if not self._service_future.done():
            QTimer.singleShot(50, partial(self._finish_autostart, enabled))
            return
        try:
            ok, error = self._service_future.result()
        except Exception as exc:
            ok, error = False, str(exc)
        self._service_future = None
        if not ok:
            QMessageBox.warning(self, "Startup settings", error or "Operation failed")
            self._startup_switch.blockSignals(True)
            self._startup_switch.setChecked(not enabled)
            self._startup_switch.blockSignals(False)
        self._startup_switch.setEnabled(True)
        self.settings["app"]["auto_restore"] = ok and enabled
        self._flush_save()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _flush_save(self) -> None:
        self._save_timer.stop()
        try:
            store.save(self.settings)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Could not save settings: {exc}", 5000)

    def _start_preview(self) -> None:
        path = self.camera.path.encode()
        device = next(
            (item for item in QMediaDevices.videoInputs() if path in bytes(item.id())), None
        )
        if device is not None:
            self._qt_camera = QCamera(device)
            camera_format = select_preview_format(device.videoFormats())
            if camera_format is not None:
                self._qt_camera.setCameraFormat(camera_format)
                resolution = camera_format.resolution()
                self.statusBar().showMessage(
                    f"Preview: {resolution.width()}×{resolution.height()} at "
                    f"up to {camera_format.maxFrameRate():g} fps",
                    5000,
                )
            self._capture_session.setCamera(self._qt_camera)
            self._qt_camera.start()

    def _stop_preview(self) -> None:
        if self._qt_camera is not None:
            self._qt_camera.stop()
            self._qt_camera.deleteLater()
            self._qt_camera = None

    def _schedule_refresh(self, _path: str) -> None:
        self._refresh_timer.start()

    def _refresh_devices(self) -> None:
        selected = self.camera.key if self.camera else None
        try:
            change = self.registry.refresh()
        except OSError as exc:
            self.statusBar().showMessage(f"Could not refresh cameras: {exc}", 5000)
            return
        self.cameras = list(change.devices)
        self._update_picker(selected)
        if selected not in {camera.key for camera in self.cameras}:
            self._stop_preview()
            if self.cameras:
                self._select_camera(self.cameras[0])
            else:
                self.camera = None
                self._show_empty()
        for removed in change.removed:
            try:
                removed.close()
            except OSError as exc:
                self.statusBar().showMessage(f"Could not close camera: {exc}", 5000)

    def _show_empty(self) -> None:
        self.reset_button.setEnabled(False)
        self.controls_scroll.setWidget(
            QLabel("Connect a UVC webcam; it will appear automatically.")
        )

    def _report_restore(self, action, result) -> None:
        self.statusBar().showMessage(
            f"{action}: {len(result.applied)} applied, {len(result.failed)} failed", 5000
        )

    def closeEvent(self, event) -> None:
        self._stop_preview()
        self._flush_save()
        self.registry.close()
        self._service_executor.shutdown(wait=False, cancel_futures=False)
        super().closeEvent(event)


def main(argv=None) -> int:
    app = QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("Logioki")
    app.setApplicationDisplayName("Logioki")
    app.setOrganizationName("Solpulse")
    app.setOrganizationDomain("github.com/solpulse")
    app.setWindowIcon(application_icon())
    QGuiApplication.setDesktopFileName(APP_ID)
    window = KdeMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
