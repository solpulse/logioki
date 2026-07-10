import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import service


class RestoreServiceTests(unittest.TestCase):
    def test_install_writes_retrying_unit_and_enables_it(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            unit_path = os.path.join(directory, "logioki-restore.service")
            with (
                mock.patch.object(service, "SYSTEMD_UNIT", Path(unit_path)),
                mock.patch.object(service, "_systemctl") as systemctl,
            ):
                ok, error = service.install_restore_service()
            self.assertTrue(ok, error)
            with open(unit_path) as f:
                unit = f.read()
            self.assertIn("--apply --retry=30", unit)
            self.assertIn("WantedBy=default.target", unit)
            self.assertIn("NoNewPrivileges=yes", unit)
            self.assertIn("CapabilityBoundingSet=\n", unit)
            self.assertIn("PrivateNetwork=yes", unit)
            self.assertIn("ProtectProc=invisible", unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("ProtectHome=read-only", unit)
            self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
            self.assertIn("MemoryDenyWriteExecute=yes", unit)
            self.assertIn("SystemCallFilter=~", unit)
            self.assertIn("UMask=0077", unit)
            self.assertNotIn("PrivateDevices=yes", unit)
            self.assertEqual(("daemon-reload",), systemctl.call_args_list[0].args)
            self.assertEqual(("enable", service.UNIT_NAME), systemctl.call_args_list[1].args)

    def test_systemd_quote_escapes_specifiers_and_rejects_newlines(self):
        self.assertEqual('"100%% ready"', service._systemd_quote("100% ready"))
        with self.assertRaises(ValueError):
            service._systemd_quote("bad\nvalue")

    def test_systemctl_uses_an_absolute_trusted_path(self):
        with mock.patch.object(service.subprocess, "run") as run:
            service._systemctl("daemon-reload")
        command = run.call_args.args[0]
        self.assertTrue(os.path.isabs(command[0]))
        self.assertEqual("--user", command[1])


if __name__ == "__main__":
    unittest.main()
