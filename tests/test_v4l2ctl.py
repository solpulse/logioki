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


if __name__ == "__main__":
    unittest.main()
