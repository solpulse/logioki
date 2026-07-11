import logging
import unittest
from pathlib import Path
from types import SimpleNamespace

import diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_redaction_removes_home_paths_and_embedded_serials(self):
        message = f"failed for usb:046d:0944:SECRET at {Path.home()}/private/settings.json"
        redacted = diagnostics.redact(message)
        self.assertNotIn("SECRET", redacted)
        self.assertNotIn(str(Path.home()), redacted)
        self.assertIn("usb:046d:0944:redacted-", redacted)

    def test_bus_identity_is_hashed_as_a_whole(self):
        identity = "bus:Camera Name:usb-0000:00:14.0-1"
        redacted = diagnostics.redact_identity(identity)
        self.assertNotIn("Camera Name", redacted)
        self.assertNotIn("00:14.0", redacted)
        self.assertRegex(redacted, r"^bus:redacted-[0-9a-f]{10}$")

    def test_log_formatter_redacts_before_writing(self):
        record = logging.LogRecord(
            "logioki",
            logging.ERROR,
            __file__,
            1,
            "camera usb:046d:0944:SECRET failed",
            (),
            None,
        )
        self.assertNotIn("SECRET", diagnostics.RedactingFormatter("%(message)s").format(record))

    def test_camera_report_includes_driver_and_unsupported_controls(self):
        camera = SimpleNamespace(
            key="usb:046d:0944:SECRET",
            card="MX Brio",
            path="/dev/video2",
            driver="uvcvideo",
            bus_info="usb-0000:00:14.0-1",
            controls=[
                SimpleNamespace(
                    id=1,
                    name="Brightness",
                    read_only=False,
                    inactive=False,
                )
            ],
            unsupported_controls=[
                SimpleNamespace(id=2, name="Vendor mode", reason="Unsupported V4L2 type 6")
            ],
        )

        report = diagnostics.camera_report(
            camera,
            {"state": "Connected"},
            ["recent error"],
            control_values={"1": 42},
        )

        self.assertEqual("uvcvideo", report["camera"]["driver"])
        self.assertEqual("Brightness", report["supported_controls"][0]["name"])
        self.assertEqual(42, report["supported_controls"][0]["current"])
        self.assertEqual("Vendor mode", report["unsupported_controls"][0]["name"])
        self.assertNotIn("SECRET", report["camera"]["identity"])


if __name__ == "__main__":
    unittest.main()
