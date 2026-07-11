import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

import application_view_model as view_model
import models
import settings_repository
import store
import v4l2ctl


class FakeCamera:
    path = "/dev/video-test"
    card = "Test Camera"
    key = "usb:1234:5678:serial"
    identity_label = "serial"
    bus_info = "usb-test"

    def __init__(self):
        self.control = SimpleNamespace(
            id=7,
            name="Brightness",
            type=v4l2ctl.TYPE_INT,
            minimum=0,
            maximum=100,
            step=1,
            default=50,
            inactive=False,
            read_only=False,
            menu_items=[],
        )
        self.controls = [self.control]
        self.groups = {"User Controls": self.controls}
        self.values = {7: 50}
        self.closed = False

    def get(self, control_id):
        return self.values[control_id]

    def set(self, control_id, value):
        self.values[control_id] = min(value, 80)

    def refresh_flags(self):
        return None

    def close(self):
        self.closed = True


class ApplicationViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_idle(self, model, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if not model.busy:
                self.app.processEvents()
                if not model.busy:
                    return
            time.sleep(0.005)
        self.fail("view model did not become idle")

    def make_model(
        self,
        camera,
        discover=None,
        settings=None,
        repository=None,
        firmware=None,
        startup=None,
    ):
        settings = settings or store._empty_data()
        default_startup = mock.Mock()
        default_startup.restore_enabled.return_value = False
        default_startup.open_gui_enabled.return_value = False
        patches = (
            mock.patch.object(settings_repository.store, "load", return_value=settings),
            mock.patch.object(settings_repository.store, "save"),
            mock.patch.object(view_model, "StartupManager", return_value=default_startup),
            mock.patch.object(view_model.QMediaDevices, "videoInputs", return_value=[]),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        model = view_model.ApplicationViewModel(
            discover=discover or (lambda: [camera]),
            settings_repository=repository,
            firmware_provider=firmware,
            startup_manager=startup,
        )
        self.wait_idle(model)
        return model

    def test_control_write_uses_readback_and_marks_preset_modified(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        model.setControl("7", 95, True)
        self.wait_idle(model)
        self.assertEqual(80, camera.values[7])
        self.assertEqual(80, model._entry["controls"]["7"])
        self.assertEqual("Streaming — Modified", model.activePreset)
        model.shutdown()

    def test_first_discovery_reads_without_writing_current_values_back(self):
        camera = FakeCamera()
        camera.set = mock.Mock(wraps=camera.set)

        model = self.make_model(camera)

        camera.set.assert_not_called()
        self.assertEqual(50, model.controlModel._items[0].value)
        model.shutdown()

    def test_startup_restore_persists_verified_clamped_value(self):
        camera = FakeCamera()
        settings = store._empty_data()
        entry = store.camera_entry(settings, camera)
        entry["controls"]["7"] = 95

        model = self.make_model(camera, settings=settings)

        self.assertEqual(80, camera.values[7])
        self.assertEqual(80, model._entry["controls"]["7"])
        self.assertEqual(80, model.controlModel._items[0].value)
        model.shutdown()

    def test_slider_writes_coalesce_to_one_in_flight_and_latest_pending_value(self):
        camera = FakeCamera()
        calls = []

        def slow_set(control_id, value):
            calls.append(value)
            time.sleep(0.04)
            camera.values[control_id] = value

        camera.set = slow_set
        model = self.make_model(camera)
        calls.clear()
        model.setControl("7", 60, False)
        deadline = time.monotonic() + 1
        while not calls and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertEqual([60], calls)

        model.setControl("7", 70, False)
        model.setControl("7", 75, True)
        self.wait_idle(model)

        self.assertEqual([60, 75], calls)
        self.assertEqual(75, model.controlModel._items[0].value)
        model.shutdown()

    def test_control_worker_failure_does_not_stall_later_writes(self):
        camera = FakeCamera()
        original_get = camera.get
        model = self.make_model(camera)
        camera.get = mock.Mock(side_effect=OSError(5, "readback failed"))

        with self.assertLogs(view_model.LOGGER, level="ERROR"):
            model.setControl("7", 60, True)
            self.wait_idle(model)
        self.assertEqual(0, model._control_writes_active)

        camera.get = original_get
        model.setControl("7", 65, True)
        self.wait_idle(model)
        self.assertEqual(65, model.controlModel._items[0].value)
        model.shutdown()

    def test_rejected_control_write_resynchronizes_visible_state(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        messages = []
        model.notification.connect(lambda title, detail: messages.append((title, detail)))

        def reject(_control_id, _value):
            raise OSError(16, "camera is busy")

        camera.set = reject
        model.setControl("7", 90, True)
        self.wait_idle(model)

        self.assertEqual(50, model._entry["controls"]["7"])
        self.assertEqual(50, model.controlModel._items[0].value)
        self.assertTrue(any(title == "Camera rejected the change" for title, _ in messages))
        self.assertEqual(1, model.errorModel.rowCount())
        model.shutdown()

    def test_deleting_active_custom_preset_preserves_live_camera(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        model.createPreset("Studio")
        custom_index = next(
            index for index, item in enumerate(model.presetModel._items) if item.name == "Studio"
        )
        model.deletePreset(custom_index)
        self.assertEqual(50, camera.values[7])
        self.assertEqual("Unsaved", model.activePreset)
        model.shutdown()

    def test_editable_starter_preset_can_save_verified_current_values(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        model.setControl("7", 70, True)
        self.wait_idle(model)
        streaming_index = next(
            index
            for index, item in enumerate(model.presetModel._items)
            if item.presetId == "streaming"
        )
        model.updatePreset(streaming_index)
        self.assertEqual({"7": 70}, model._entry["presets"]["streaming"]["controls"])
        self.assertEqual("Streaming", model.activePreset)
        model.shutdown()

    def test_reset_applies_and_selects_camera_default_preset(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        model.setControl("7", 70, True)
        self.wait_idle(model)
        self.assertEqual(70, camera.values[7])

        model.resetDefaults()
        self.wait_idle(model)

        self.assertEqual(50, camera.values[7])
        self.assertEqual("Default", model.activePreset)
        self.assertEqual("default", model._entry["selected_preset"])
        model.shutdown()

    def test_preview_format_prefers_smooth_full_hd_and_retains_4k(self):
        def camera_format(width, height, fps, pixel_format=None):
            return SimpleNamespace(
                resolution=lambda: QSize(width, height),
                maxFrameRate=lambda: fps,
                pixelFormat=lambda: pixel_format,
            )

        selected = view_model.select_preview_format(
            [
                camera_format(1280, 720, 60),
                camera_format(1920, 1080, 60),
                camera_format(3840, 2160, 30),
            ]
        )
        self.assertEqual((1920, 1080), selected.resolution().toTuple())
        self.assertEqual(60, selected.maxFrameRate())

        modes = view_model.available_preview_formats(
            [camera_format(1920, 1080, 60), camera_format(3840, 2160, 30)]
        )
        self.assertEqual([(3840, 2160), (1920, 1080)], [m.resolution().toTuple() for m in modes])

    def test_preview_format_prefers_compressed_mode_when_frame_ranges_tie(self):
        def camera_format(pixel_format):
            return SimpleNamespace(
                resolution=lambda: QSize(1280, 720),
                maxFrameRate=lambda: 60,
                pixelFormat=lambda: pixel_format,
            )

        yuyv = camera_format(view_model.QVideoFrameFormat.PixelFormat.Format_YUYV)
        jpeg = camera_format(view_model.QVideoFrameFormat.PixelFormat.Format_Jpeg)

        self.assertIs(jpeg, view_model.select_preview_format([yuyv, jpeg]))
        self.assertEqual(
            "1280×720 · 60 fps · MJPEG",
            view_model.preview_format_label(jpeg),
        )

    def test_preview_device_matching_is_exact(self):
        partial = SimpleNamespace(id=lambda: b"platform:/dev/video0:stream")
        exact = SimpleNamespace(id=lambda: b"/dev/video0")
        self.assertIs(exact, view_model.find_preview_device([partial, exact], "/dev/video0"))
        self.assertIsNone(view_model.find_preview_device([partial], "/dev/video0"))

    def test_preview_busy_errors_ignore_stale_generations(self):
        preview = view_model.PreviewController()
        preview._generation = 4
        preview._set_state("Connected", "1280×720")

        preview._error(3, "device is busy")
        self.assertEqual("Connected", preview.state)
        preview._error(4, "device is busy")
        self.assertEqual("Busy", preview.state)

    def test_preview_visibility_state_is_remembered_before_camera_start(self):
        preview = view_model.PreviewController()
        camera = mock.Mock()

        preview.setVisible(False)
        preview._camera = camera
        preview.setVisible(False)
        camera.stop.assert_called_once_with()
        preview.setVisible(True)
        camera.start.assert_called_once_with()
        self.assertTrue(preview._visible)

    def test_shutdown_drains_pending_write_before_final_state(self):
        camera = FakeCamera()
        original_set = camera.set

        def slow_set(control_id, value):
            time.sleep(0.03)
            original_set(control_id, value)

        camera.set = slow_set
        model = self.make_model(camera)
        model.setControl("7", 60, True)
        model.setControl("7", 73, False)
        model.setControl("7", 73, True)
        model.shutdown()
        self.assertEqual(73, camera.values[7])
        self.assertEqual(73, model._entry["controls"]["7"])
        self.assertTrue(camera.closed)

    def test_qml_models_store_explicit_typed_records(self):
        camera = FakeCamera()
        model = self.make_model(camera)

        self.assertIsInstance(model.cameraModel._items[0], models.CameraListItem)
        self.assertIsInstance(model.controlModel._items[0], models.ControlListItem)
        self.assertIsInstance(model.presetModel._items[0], models.PresetListItem)
        model._error("typed error")
        self.assertIsInstance(model.errorModel._items[0], models.ErrorListItem)
        model.shutdown()

    def test_read_only_control_displays_live_value_without_persisting_it(self):
        camera = FakeCamera()
        read_only = SimpleNamespace(
            id=8,
            name="Sensor status",
            type=v4l2ctl.TYPE_INT,
            minimum=0,
            maximum=100,
            step=1,
            default=10,
            inactive=False,
            read_only=True,
            menu_items=[],
        )
        camera.controls.append(read_only)
        camera.groups["User Controls"].append(read_only)
        camera.values[8] = 73
        model = self.make_model(camera)

        record = next(item for item in model.controlModel._items if item.controlId == "8")
        self.assertEqual(73, record.value)
        self.assertFalse(record.available)
        self.assertNotIn("8", model._entry["controls"])
        model.shutdown()

    def test_busy_state_remains_true_until_every_queued_busy_task_finishes(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        second_started = threading.Event()
        release_second = threading.Event()

        model._submit(lambda: "first", lambda _result: None)

        def second_operation():
            second_started.set()
            release_second.wait(1)

        model._submit(second_operation, lambda _result: None)
        self.assertTrue(second_started.wait(1))
        self.app.processEvents()
        self.assertTrue(model.busy)

        release_second.set()
        self.wait_idle(model)
        self.assertFalse(model.busy)
        model.shutdown()

    def test_backend_and_persistence_work_stays_off_the_ui_thread(self):
        camera = FakeCamera()
        main_thread = threading.get_ident()
        observed = []
        settings = store._empty_data()

        class RecordingRepository(settings_repository.SettingsRepository):
            def load(self):
                observed.append(("load", threading.get_ident()))
                return settings

            def save(self, data):
                observed.append(("save", threading.get_ident()))

            def capture(self, selected_camera, include_read_only=False):
                observed.append(("capture", threading.get_ident()))
                return super().capture(selected_camera, include_read_only)

        class RecordingFirmware:
            def state_for(self, _camera):
                observed.append(("firmware", threading.get_ident()))
                return view_model.FirmwareState(False, "Unavailable", "Unsupported")

        class RecordingStartup:
            def load_state(self, _restore, _open):
                observed.append(("startup", threading.get_ident()))

            def restore_enabled(self):
                observed.append(("startup", threading.get_ident()))
                return False

            def open_gui_enabled(self):
                observed.append(("startup", threading.get_ident()))
                return False

        original_set = camera.set

        def record_set(control_id, value):
            observed.append(("set", threading.get_ident()))
            original_set(control_id, value)

        camera.set = record_set

        def discover():
            observed.append(("discover", threading.get_ident()))
            return [camera]

        model = self.make_model(
            camera,
            discover=discover,
            repository=RecordingRepository(),
            firmware=RecordingFirmware(),
            startup=RecordingStartup(),
        )
        model.setControl("7", 60, True)
        self.wait_idle(model)
        model.shutdown()

        labels = {label for label, _thread_id in observed}
        self.assertTrue(
            {"load", "save", "capture", "firmware", "startup", "discover", "set"} <= labels,
            labels,
        )
        self.assertTrue(all(thread_id != main_thread for _label, thread_id in observed))

    def test_diagnostics_export_runs_off_the_ui_thread(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        observed = []

        def record_export(_path, _report):
            observed.append(threading.get_ident())

        with mock.patch.object(view_model.diagnostics, "export_report", side_effect=record_export):
            model.exportDiagnostics("/tmp/logioki-thread-test.json")
            self.wait_idle(model)

        self.assertEqual(1, len(observed))
        self.assertNotEqual(threading.get_ident(), observed[0])
        model.shutdown()

    def test_shutdown_closes_cameras_when_final_persistence_fails(self):
        camera = FakeCamera()

        class FailingRepository(settings_repository.SettingsRepository):
            def load(self):
                return store._empty_data()

            def save(self, _data):
                raise OSError(5, "storage unavailable")

        with self.assertLogs(view_model.LOGGER, level="ERROR"):
            model = self.make_model(camera, repository=FailingRepository())
            model.shutdown()

        self.assertTrue(camera.closed)

    def test_export_diagnostics_decodes_local_file_url(self):
        camera = FakeCamera()
        model = self.make_model(camera)
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            target = os.path.join(directory, "camera report.json")
            model.exportDiagnostics(view_model.QUrl.fromLocalFile(target).toString())
            self.wait_idle(model)
            self.assertTrue(os.path.isfile(target))
        model.shutdown()

    def test_hotplug_replacement_closes_old_descriptor_and_reselects(self):
        original = FakeCamera()
        replacement = FakeCamera()
        replacement.path = "/dev/video4"
        state = [original]
        model = self.make_model(original, discover=lambda: list(state))

        state[:] = [replacement]
        model.refreshDevices()
        self.wait_idle(model)

        self.assertTrue(original.closed)
        self.assertIs(replacement, model._camera)
        self.assertEqual("/dev/video4", model._camera.path)
        model.shutdown()

    def test_disconnect_and_reconnect_rebuilds_camera_state(self):
        original = FakeCamera()
        replacement = FakeCamera()
        state = [original]
        model = self.make_model(original, discover=lambda: list(state))

        state.clear()
        model.refreshDevices()
        self.wait_idle(model)
        self.assertFalse(model.hasCamera)
        self.assertEqual("No camera", model.connectionState)
        self.assertTrue(original.closed)

        state.append(replacement)
        model.refreshDevices()
        self.wait_idle(model)
        self.assertTrue(model.hasCamera)
        self.assertIs(replacement, model._camera)
        model.shutdown()

    def test_multiple_camera_selection_preserves_distinct_identity(self):
        first = FakeCamera()
        second = FakeCamera()
        second.key = "usb:1234:5678:second"
        second.path = "/dev/video-second"
        second.identity_label = "second"
        model = self.make_model(first, discover=lambda: [first, second])

        self.assertEqual(2, model.cameraModel.rowCount())
        model.selectCamera(1)
        self.wait_idle(model)
        self.assertIs(second, model._camera)
        self.assertEqual(1, model.selectedCamera)
        model.shutdown()

    def test_initial_discovery_hides_and_closes_duplicate_video_nodes(self):
        first = FakeCamera()
        duplicate = FakeCamera()
        duplicate.path = "/dev/video-duplicate"
        model = self.make_model(first, discover=lambda: [first, duplicate])

        self.assertEqual(1, model.cameraModel.rowCount())
        self.assertIs(first, model._camera)
        self.assertTrue(duplicate.closed)
        model.shutdown()


if __name__ == "__main__":
    unittest.main()
