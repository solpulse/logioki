import unittest
from types import SimpleNamespace
from unittest import mock

import logioki


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


if __name__ == "__main__":
    unittest.main()
