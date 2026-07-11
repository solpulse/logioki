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
            self.assertIn('"--apply" "--retry=30"', unit)
            self.assertIn("ConditionPathExists=!", unit)
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

    def test_appimage_restore_uses_persistent_launcher_path(self):
        with mock.patch.dict(os.environ, {"APPIMAGE": "/opt/Logioki AppImage"}, clear=True):
            command = service._restore_command()

        self.assertEqual(
            ["/opt/Logioki AppImage", "--apply", "--retry=30"],
            command,
        )
        unit = service._unit_contents(command)
        self.assertIn('ExecStart="/opt/Logioki AppImage" "--apply" "--retry=30"', unit)

    def test_systemctl_uses_an_absolute_trusted_path(self):
        with mock.patch.object(service.subprocess, "run") as run:
            service._systemctl("daemon-reload")
        command = run.call_args.args[0]
        self.assertTrue(os.path.isabs(command[0]))
        self.assertEqual("--user", command[1])

    def test_remove_disables_deletes_and_reloads_unit(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            unit = Path(directory) / service.UNIT_NAME
            unit.write_text("unit", encoding="utf-8")
            completed = mock.Mock(returncode=0, stderr="")
            with (
                mock.patch.object(service, "SYSTEMD_UNIT", unit),
                mock.patch.object(service, "_systemctl", return_value=completed) as systemctl,
            ):
                self.assertEqual((True, None), service.remove_restore_service())
        self.assertEqual(("disable", service.UNIT_NAME), systemctl.call_args_list[0].args)
        self.assertEqual(("daemon-reload",), systemctl.call_args_list[1].args)

    def test_enabled_requires_installed_unit_and_systemd_confirmation(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            unit = Path(directory) / service.UNIT_NAME
            with mock.patch.object(service, "SYSTEMD_UNIT", unit):
                self.assertFalse(service.is_restore_service_enabled())
            unit.touch()
            with (
                mock.patch.object(service, "SYSTEMD_UNIT", unit),
                mock.patch.object(service, "_systemctl", return_value=mock.Mock(returncode=1)),
            ):
                self.assertFalse(service.is_restore_service_enabled())


if __name__ == "__main__":
    unittest.main()
