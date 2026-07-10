import unittest
from types import SimpleNamespace
from unittest import mock

import logioki
from device_monitor import DeviceRegistry


class ControllerTests(unittest.TestCase):
    def test_slider_writes_are_coalesced_to_latest_value(self):
        controller = object.__new__(logioki.WindowController)
        controller._updating = False
        controller._pending_controls = {}
        controller._control_timeout = 0
        controller._apply = mock.Mock()
        control = SimpleNamespace(id=7)

        with mock.patch.object(logioki.GLib, "timeout_add", return_value=11) as timeout_add:
            controller._queue_control_write(control, 10)
            controller._queue_control_write(control, 20)

        timeout_add.assert_called_once()
        controller._on_control_timeout()
        controller._apply.assert_called_once_with(control, 20)

    def test_sync_guard_is_restored_when_camera_refresh_fails(self):
        controller = object.__new__(logioki.WindowController)
        controller._updating = False
        controller.camera = mock.Mock()
        controller.camera.refresh_flags.side_effect = OSError("disconnected")
        controller.rows = {}

        with self.assertRaises(OSError):
            controller._sync_from_camera()
        self.assertFalse(controller._updating)

    def test_shutdown_releases_resources_when_final_save_fails(self):
        controller = object.__new__(logioki.WindowController)
        camera = mock.Mock(path="/dev/video0")
        controller._closed = False
        controller._save_timeout = 0
        controller._device_refresh_timeout = 0
        controller._device_monitor = None
        controller._device_registry = DeviceRegistry(lambda: (), [camera])
        controller._flush_control_writes = mock.Mock()
        controller._flush_save = mock.Mock(side_effect=OSError("disk full"))
        controller.preview = mock.Mock()
        controller._save_executor = mock.Mock()

        with self.assertLogs(logioki.LOGGER, level="ERROR"):
            self.assertFalse(controller._on_close(None))

        controller.preview.stop.assert_called_once_with()
        controller._save_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)
        camera.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
