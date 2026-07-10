import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication, QComboBox, QSpinBox

    import kde_qt
except ModuleNotFoundError:
    QApplication = None
    kde_qt = None


@unittest.skipUnless(QApplication, "PySide6 KDE extra is not installed")
class KdeQtSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_empty_window_constructs_and_closes(self):
        settings = {
            "version": 2,
            "app": {"auto_restore": False},
            "cameras": {},
            "legacy_cameras": {},
        }
        with (
            mock.patch.object(kde_qt.v4l2ctl, "list_cameras", return_value=[]),
            mock.patch.object(kde_qt.store, "load", return_value=settings),
            mock.patch.object(kde_qt.store, "save") as save,
        ):
            window = kde_qt.KdeMainWindow()
            self.assertFalse(window.reset_button.isEnabled())
            self.assertEqual(0, window.device_picker.count())
            self.assertEqual("Reset defaults", window.reset_button.text())
            self.assertIn("factory default", window.reset_button.toolTip())
            self.assertGreaterEqual(window.controls_scroll.minimumWidth(), 380)
            self.assertEqual(
                kde_qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
                window.controls_scroll.horizontalScrollBarPolicy(),
            )
            self.assertFalse(window.windowIcon().isNull())
            window.close()
        save.assert_called_once_with(settings)

    def test_integer_control_updates_camera_and_persistent_model(self):
        control = SimpleNamespace(
            id=7,
            name="Brightness",
            type=kde_qt.v4l2ctl.TYPE_INT,
            minimum=0,
            maximum=100,
            step=1,
            default=50,
            inactive=False,
            read_only=False,
            menu_items=[],
        )

        class Camera:
            path = "/dev/video-test"
            card = "Test Camera"
            key = "test:camera"
            identity_label = "test"
            controls = [control]
            groups = {"Image": controls}

            def __init__(self):
                self.value = 50

            def get(self, _control_id):
                return self.value

            def set(self, _control_id, value):
                self.value = value

            def refresh_flags(self):
                return None

            def close(self):
                return None

        camera = Camera()
        settings = {
            "version": 2,
            "app": {"auto_restore": False},
            "cameras": {},
            "legacy_cameras": {},
        }
        with (
            mock.patch.object(kde_qt.v4l2ctl, "list_cameras", return_value=[camera]),
            mock.patch.object(kde_qt.store, "load", return_value=settings),
            mock.patch.object(kde_qt.store, "save"),
            mock.patch.object(kde_qt.QMediaDevices, "videoInputs", return_value=[]),
        ):
            window = kde_qt.KdeMainWindow()
            spin = window.findChild(QSpinBox)
            self.assertIsNotNone(spin)
            spin.setValue(72)
            self.app.processEvents()
            self.assertEqual(72, camera.value)
            self.assertEqual(72, window.camera_settings["controls"]["7"])
            window.close()

    def test_menu_change_defers_rebuild_until_native_signal_returns(self):
        control = SimpleNamespace(
            id=8,
            name="Power Line Frequency",
            type=kde_qt.v4l2ctl.TYPE_MENU,
            minimum=0,
            maximum=2,
            step=1,
            default=1,
            inactive=False,
            read_only=False,
            menu_items=[(0, "Disabled"), (1, "50 Hz"), (2, "60 Hz")],
        )

        class Camera:
            path = "/dev/video-test"
            card = "Test Camera"
            key = "test:menu-camera"
            identity_label = "test"
            controls = [control]
            groups = {"Image": controls}

            def __init__(self):
                self.value = 1

            def get(self, _control_id):
                return self.value

            def set(self, _control_id, value):
                self.value = value

            def refresh_flags(self):
                return None

            def close(self):
                return None

        camera = Camera()
        settings = {
            "version": 2,
            "app": {"auto_restore": False},
            "cameras": {},
            "legacy_cameras": {},
        }
        with (
            mock.patch.object(kde_qt.v4l2ctl, "list_cameras", return_value=[camera]),
            mock.patch.object(kde_qt.store, "load", return_value=settings),
            mock.patch.object(kde_qt.store, "save"),
            mock.patch.object(kde_qt.QMediaDevices, "videoInputs", return_value=[]),
        ):
            window = kde_qt.KdeMainWindow()
            panel = window.controls_scroll.widget()
            menu = next(
                combo for combo in panel.findChildren(QComboBox) if combo.findText("60 Hz") >= 0
            )
            menu.setCurrentIndex(menu.findText("60 Hz"))
            self.assertIs(panel, window.controls_scroll.widget())
            self.assertTrue(window._rebuild_timer.isActive())
            self.app.processEvents()
            self.assertEqual(2, camera.value)
            self.assertIsNot(panel, window.controls_scroll.widget())
            for value in (1, 2) * 10:
                panel = window.controls_scroll.widget()
                menu = next(
                    combo for combo in panel.findChildren(QComboBox) if combo.findText("60 Hz") >= 0
                )
                menu.setCurrentIndex(menu.findData(value))
                self.app.processEvents()
            self.assertEqual(2, camera.value)
            window.close()

    def test_preview_format_prefers_720p_high_frame_rate(self):
        def camera_format(width, height, fps):
            return SimpleNamespace(
                resolution=lambda: QSize(width, height),
                maxFrameRate=lambda: fps,
            )

        formats = [
            camera_format(3840, 2160, 30.0),
            camera_format(1280, 720, 30.0),
            camera_format(1280, 720, 60.0),
            camera_format(1920, 1080, 60.0),
        ]
        selected = kde_qt.select_preview_format(formats)
        self.assertEqual(QSize(1280, 720), selected.resolution())
        self.assertEqual(60.0, selected.maxFrameRate())


if __name__ == "__main__":
    unittest.main()
