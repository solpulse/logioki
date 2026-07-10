"""Opt-in integration checks for an actual V4L2 camera.

Set LOGIOKI_TEST_CAMERA=/dev/videoN to include these in a hardware test run.
"""

import os
import unittest

import v4l2ctl

DEVICE = os.environ.get("LOGIOKI_TEST_CAMERA")


@unittest.skipUnless(DEVICE, "set LOGIOKI_TEST_CAMERA to test real hardware")
class HardwareIntegrationTests(unittest.TestCase):
    def test_enumeration_and_non_mutating_control_reads(self):
        with v4l2ctl.Camera(DEVICE) as camera:
            self.assertTrue(camera.is_capture)
            self.assertTrue(camera.controls)
            for control in camera.controls:
                if not control.inactive:
                    value = camera.get(control.id)
                    self.assertGreaterEqual(value, control.minimum)
                    self.assertLessEqual(value, control.maximum)


if __name__ == "__main__":
    unittest.main()
