#!/usr/bin/env python3
"""Logioki — webcam control panel for Linux (UVC / Logitech).

GUI:       python3 logioki.py
Headless:  python3 logioki.py --apply   (restore saved settings, used at login)
"""

import sys

import v4l2ctl  # noqa: F401
from desktop import detect_desktop

# Keep the login service independent of GTK/GStreamer availability while making
# normal module imports side-effect free.
if __name__ == "__main__" and "--apply" in sys.argv:
    from logioki_cli import main as _cli_main

    sys.exit(_cli_main())


import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402, F401

try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: E402
except (ImportError, ValueError):
    Adw = None

from controller import LOGGER, WindowController, camera_labels  # noqa: E402, F401
from preview import Preview  # noqa: E402, F401

APP_ID = "io.github.solpulse.Logioki"


def _set_accessible_label(widget, label):
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


DESKTOP = detect_desktop()
USE_ADWAITA = DESKTOP == "gnome" and Adw is not None


def install_kde_css():
    display = Gdk.Display.get_default()
    if display is None:
        return

    css = b"""
    .kde-root { background: @theme_bg_color; }

    .kde-header-title { font-weight: 600; }
    .kde-header-subtitle {
        color: alpha(@theme_fg_color, 0.64);
        font-size: 0.82em;
    }

    .kde-preview-pane { padding: 22px; }
    .kde-preview-heading {
        font-size: 1.18em;
        font-weight: 600;
    }
    .kde-preview-subtitle { color: alpha(@theme_fg_color, 0.64); }
    .kde-preview-frame {
        background: #111111;
        border: 1px solid alpha(@theme_fg_color, 0.16);
        border-radius: 12px;
    }
    .kde-preview { background: #111111; border-radius: 12px; }
    .kde-live-badge {
        margin: 12px;
        padding: 5px 10px;
        border-radius: 999px;
        background: rgba(0, 0, 0, 0.68);
        color: white;
        font-size: 0.82em;
        font-weight: 600;
    }
    .kde-preview-footer {
        margin-top: 4px;
        padding: 12px 14px;
        border: 1px solid alpha(@theme_fg_color, 0.10);
        border-radius: 10px;
        background: alpha(@theme_base_color, 0.72);
    }
    .kde-hint { color: alpha(@theme_fg_color, 0.66); font-size: 0.88em; }

    .kde-inspector {
        border-left: 1px solid @borders;
        background: alpha(@theme_base_color, 0.38);
    }
    .kde-tabbar {
        padding: 12px 14px;
        border-bottom: 1px solid @borders;
        background: @theme_base_color;
    }
    .kde-page { padding: 18px 16px 28px; }
    .kde-page-heading {
        margin-bottom: 3px;
        font-size: 1.35em;
        font-weight: 600;
    }
    .kde-page-description {
        margin-bottom: 16px;
        color: alpha(@theme_fg_color, 0.64);
    }
    .kde-group {
        margin-bottom: 16px;
        border: 1px solid alpha(@theme_fg_color, 0.13);
        border-radius: 10px;
        background: @theme_base_color;
    }
    .kde-group-title {
        padding: 11px 14px 9px;
        color: alpha(@theme_fg_color, 0.70);
        font-size: 0.86em;
        font-weight: 600;
    }
    .kde-row {
        min-height: 48px;
        padding: 9px 14px;
        border-top: 1px solid alpha(@theme_fg_color, 0.08);
    }
    .kde-row-title { font-weight: 500; }
    .kde-row-subtitle {
        color: alpha(@theme_fg_color, 0.62);
        font-size: 0.84em;
    }
    .kde-preset-hero {
        margin-bottom: 16px;
        padding: 16px;
        border: 1px solid alpha(@theme_selected_bg_color, 0.38);
        border-radius: 10px;
        background: alpha(@theme_selected_bg_color, 0.08);
    }
    .kde-preset-name { font-size: 1.08em; font-weight: 600; }
    .kde-notification {
        margin: 0 18px 18px;
        padding: 10px 14px;
        border: 1px solid alpha(@theme_fg_color, 0.18);
        border-radius: 9px;
        background: @theme_base_color;
        color: @theme_fg_color;
    }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


if Adw is not None:
    from gnome_view import GnomeWindow

from kde_view import KdeWindow  # noqa: E402

ApplicationBase = Adw.Application if USE_ADWAITA else Gtk.Application
WindowClass = GnomeWindow if USE_ADWAITA else KdeWindow


class App(ApplicationBase):
    def __init__(self):
        ApplicationBase.__init__(
            self,
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_startup(self):
        ApplicationBase.do_startup(self)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._quit_cleanly)
        self.add_action(quit_action)
        close_action = Gio.SimpleAction.new("close", None)
        close_action.connect("activate", self._close_active_window)
        self.add_action(close_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("app.close", ["<Primary>w"])
        if USE_ADWAITA:
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)
        else:
            install_kde_css()

    def do_activate(self):
        win = self.get_active_window() or WindowClass(self)
        win.present()

    def _close_active_window(self, _action, _parameter):
        window = self.get_active_window()
        if window is not None:
            window.close()

    def _quit_cleanly(self, _action, _parameter):
        windows = list(self.get_windows())
        if not windows:
            self.quit()
            return
        for window in windows:
            window.close()


def main(argv=None):
    # Keep one command-line policy in the dependency-light entry-point module.
    from logioki_cli import main as cli_main

    return cli_main(sys.argv if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
