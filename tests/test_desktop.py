import os
import unittest
from unittest import mock

import desktop


class DesktopDetectionTests(unittest.TestCase):
    def test_explicit_style_wins(self):
        with mock.patch.dict(os.environ, {"LOGIOKI_DESKTOP_STYLE": "kde"}, clear=True):
            self.assertEqual("kde", desktop.detect_desktop())

    def test_plasma_session_selects_kde(self):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True):
            self.assertEqual("kde", desktop.detect_desktop())

    def test_unknown_session_uses_gnome_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual("gnome", desktop.detect_desktop())

    def test_macos_uses_the_future_platform_profile(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(desktop.sys, "platform", "darwin"),
        ):
            self.assertEqual("macos", desktop.detect_desktop())


if __name__ == "__main__":
    unittest.main()
