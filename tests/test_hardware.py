"""Opt-in integration checks for an actual V4L2 camera.

Set LOGIOKI_TEST_CAMERA=/dev/videoN to include these in a hardware test run.
"""

import os
import unittest

import v4l2ctl

DEVICE = os.environ.get("LOGIOKI_TEST_CAMERA")
EXPECTED_MODEL = os.environ.get("LOGIOKI_EXPECT_CAMERA")


@unittest.skipUnless(DEVICE, "set LOGIOKI_TEST_CAMERA to test real hardware")
class HardwareIntegrationTests(unittest.TestCase):
    def test_enumeration_and_non_mutating_control_reads(self):
        with v4l2ctl.Camera(DEVICE) as camera:
            self.assertTrue(camera.is_capture)
            self.assertTrue(camera.controls)
            if EXPECTED_MODEL:
                self.assertIn(EXPECTED_MODEL.casefold(), camera.card.casefold())
            for control in camera.controls:
                if not control.inactive:
                    value = camera.get(control.id)
                    self.assertGreaterEqual(value, control.minimum)
                    self.assertLessEqual(value, control.maximum)

    def test_qt_multimedia_exact_device_and_preview_format(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtMultimedia import QMediaDevices, QVideoFrameFormat

        from application_view_model import find_preview_device, select_preview_format

        _app = QGuiApplication.instance() or QGuiApplication([])
        device = find_preview_device(QMediaDevices.videoInputs(), DEVICE)
        self.assertIsNotNone(device, f"Qt Multimedia did not expose exact device {DEVICE}")
        self.assertIn("MX Brio", device.description())
        camera_format = select_preview_format(device.videoFormats())
        self.assertIsNotNone(camera_format)
        self.assertEqual((1280, 720), camera_format.resolution().toTuple())
        self.assertEqual(
            QVideoFrameFormat.PixelFormat.Format_Jpeg,
            camera_format.pixelFormat(),
        )

    def test_writable_controls_verify_same_value_round_trip(self):
        with v4l2ctl.Camera(DEVICE) as camera:
            verified = 0
            camera.refresh_flags()
            for control in camera.controls:
                if control.inactive or control.read_only:
                    continue
                current = camera.get(control.id)
                camera.set(control.id, current)
                self.assertEqual(current, camera.get(control.id), control.name)
                verified += 1
            self.assertGreater(verified, 0, "camera exposes no writable active controls")


if __name__ == "__main__":
    unittest.main()
