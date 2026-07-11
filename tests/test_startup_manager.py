import tempfile
import unittest
from pathlib import Path
from unittest import mock

import startup_manager


class StartupManagerTests(unittest.TestCase):
    def test_desktop_exec_quote_handles_spaces_and_rejects_newlines(self):
        self.assertEqual(
            '"/opt/My App/logioki"',
            startup_manager._desktop_exec_quote("/opt/My App/logioki"),
        )
        self.assertEqual('"100%% ready"', startup_manager._desktop_exec_quote("100% ready"))
        with self.assertRaises(ValueError):
            startup_manager._desktop_exec_quote("bad\ncommand")

    def test_appimage_gui_autostart_uses_persistent_launcher_path(self):
        with mock.patch.dict("os.environ", {"APPIMAGE": "/opt/Logioki AppImage"}, clear=True):
            self.assertEqual(["/opt/Logioki AppImage"], startup_manager._gui_command())
            self.assertIn('Exec="/opt/Logioki AppImage"', startup_manager._desktop_contents())

    def test_gui_autostart_is_independent_and_atomic(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            target = Path(directory) / "autostart" / "io.github.solpulse.Logioki.desktop"
            with (
                mock.patch.object(startup_manager, "AUTOSTART_DIR", target.parent),
                mock.patch.object(startup_manager, "AUTOSTART_FILE", target),
            ):
                manager = startup_manager.StartupManager()
                self.assertEqual((True, None), manager.set_open_gui_enabled(True))
                self.assertTrue(manager.open_gui_enabled())
                self.assertIn("Exec=", target.read_text())
                self.assertEqual((True, None), manager.set_open_gui_enabled(False))
                self.assertFalse(manager.open_gui_enabled())

    def test_flatpak_portal_coordinates_independent_settings(self):
        calls = []

        def portal_request(enabled, commandline):
            calls.append((enabled, commandline))
            return True, None

        with (
            mock.patch.dict("os.environ", {"FLATPAK_ID": "io.github.solpulse.Logioki"}),
            mock.patch.object(startup_manager.shutil, "which", return_value="/app/bin/logioki"),
        ):
            manager = startup_manager.StartupManager(portal_request=portal_request)
            manager.load_state(restore=True, open_gui=False)
            self.assertTrue(manager.restore_enabled())
            self.assertFalse(manager.open_gui_enabled())

            self.assertEqual((True, None), manager.set_open_gui_enabled(True))
            self.assertEqual((True, ["/app/bin/logioki"]), calls[-1])
            self.assertTrue(manager.restore_enabled())
            self.assertTrue(manager.open_gui_enabled())

            self.assertEqual((True, None), manager.set_open_gui_enabled(False))
            self.assertEqual((True, ["/app/bin/logioki", "--apply", "--retry=30"]), calls[-1])

            self.assertEqual((True, None), manager.set_restore_enabled(False))
            self.assertEqual((False, ["/app/bin/logioki"]), calls[-1])


if __name__ == "__main__":
    unittest.main()
