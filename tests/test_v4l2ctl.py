import unittest
from unittest import mock

import v4l2ctl


class CameraLifecycleTests(unittest.TestCase):
    def test_querycap_failure_closes_open_descriptor(self):
        with (
            mock.patch.object(v4l2ctl.os, "open", return_value=42),
            mock.patch.object(v4l2ctl.fcntl, "ioctl", side_effect=OSError(5, "query failed")),
            mock.patch.object(v4l2ctl.os, "close") as close,
            self.assertRaises(OSError),
        ):
            v4l2ctl.Camera("/dev/video0")
        close.assert_called_once_with(42)

    def test_closed_camera_rejects_control_operations(self):
        camera = object.__new__(v4l2ctl.Camera)
        camera.fd = None
        with self.assertRaises(OSError) as raised:
            camera.get(1)
        self.assertEqual(v4l2ctl.errno.EBADF, raised.exception.errno)

    def test_close_is_idempotent_even_when_os_close_fails(self):
        camera = object.__new__(v4l2ctl.Camera)
        camera.fd = 42
        with (
            mock.patch.object(v4l2ctl.os, "close", side_effect=OSError(5, "close failed")) as close,
            self.assertRaises(OSError),
        ):
            camera.close()
        camera.close()
        close.assert_called_once_with(42)

    def test_capabilities_fallback_when_device_caps_flag_is_absent(self):
        def ioctl(_fd, request, structure):
            if request == v4l2ctl.VIDIOC_QUERYCAP:
                structure.card = b"Test Camera"
                structure.bus_info = b"usb-test"
                structure.capabilities = v4l2ctl.V4L2_CAP_VIDEO_CAPTURE
                structure.device_caps = 0
                return 0
            raise OSError(v4l2ctl.errno.EINVAL, "end")

        with (
            mock.patch.object(v4l2ctl.os, "open", return_value=42),
            mock.patch.object(v4l2ctl.fcntl, "ioctl", side_effect=ioctl),
            mock.patch.object(v4l2ctl.os, "close"),
        ):
            camera = v4l2ctl.Camera("/dev/video0")
            self.assertTrue(camera.is_capture)
            camera.close()

    def test_control_enumeration_stops_if_driver_repeats_an_identifier(self):
        camera = object.__new__(v4l2ctl.Camera)
        camera.fd = 42
        camera.controls = []
        camera.groups = {}

        def ioctl(_fd, request, structure):
            self.assertEqual(v4l2ctl.VIDIOC_QUERYCTRL, request)
            structure.id = 123
            structure.type = v4l2ctl.TYPE_INT
            structure.name = b"Brightness"
            structure.minimum = 0
            structure.maximum = 100
            structure.step = 1
            return 0

        with mock.patch.object(v4l2ctl.fcntl, "ioctl", side_effect=ioctl) as mocked_ioctl:
            camera._enumerate()
        self.assertEqual(2, mocked_ioctl.call_count)
        self.assertEqual(1, len(camera.controls))


if __name__ == "__main__":
    unittest.main()
