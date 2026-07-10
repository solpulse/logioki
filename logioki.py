#!/usr/bin/env python3
"""Logioki — webcam control panel for Linux (UVC / Logitech).

GUI:       python3 logioki.py
Headless:  python3 logioki.py --apply   (restore saved settings, used at login)
"""

import copy
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import store
import v4l2ctl

# Keep the login service independent of GTK/GStreamer availability while making
# normal module imports side-effect free.
if __name__ == "__main__" and "--apply" in sys.argv:
    from logioki_cli import main as _cli_main

    sys.exit(_cli_main())


import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: E402
except (ImportError, ValueError):
    Adw = None

import service  # noqa: E402
from preview import Preview  # noqa: E402

APP_ID = "io.github.solpulse.Logioki"
LOGGER = logging.getLogger(__name__)


def _set_accessible_label(widget, label):
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


def camera_labels(cameras):
    counts = {}
    for cam in cameras:
        counts[cam.card] = counts.get(cam.card, 0) + 1
    return [
        f"{cam.card} — {cam.identity_label}" if counts[cam.card] > 1 else cam.card
        for cam in cameras
    ]


def detect_desktop():
    """Return the desktop shell whose conventions the UI should follow."""
    forced = os.environ.get("LOGIOKI_DESKTOP_STYLE", "").lower()
    if forced in ("gnome", "kde"):
        return forced

    values = [
        os.environ.get("XDG_CURRENT_DESKTOP", ""),
        os.environ.get("XDG_SESSION_DESKTOP", ""),
        os.environ.get("DESKTOP_SESSION", ""),
    ]
    desktop = ":".join(values).lower()
    if os.environ.get("KDE_FULL_SESSION") or "kde" in desktop or "plasma" in desktop:
        return "kde"
    if os.environ.get("GNOME_DESKTOP_SESSION_ID") or "gnome" in desktop:
        return "gnome"
    return "gnome"


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


class WindowController:
    def _init_controller(self):
        self.settings = store.load()
        self.cameras = v4l2ctl.list_cameras()
        self.camera = None
        self.camera_settings = None
        self.rows = {}  # ctrl_id -> (row, value_widget)
        self._updating = False  # guard against feedback loops
        self._save_timeout = 0
        self._control_timeout = 0
        self._pending_controls = {}
        self._save_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="logioki-save")
        self._service_busy = False
        self._closed = False
        self._preset_ids = []

    def _select_initial_camera(self):
        self.connect("close-request", self._on_close)
        if self.cameras:
            self._select_camera(self.cameras[0])
        else:
            self._show_no_camera()
        if self.settings.setdefault("app", {}).get("auto_restore", False):
            GLib.idle_add(self._ensure_autostart)

    # ---------- camera lifecycle ----------

    def _select_camera(self, cam):
        self._flush_control_writes()
        self.preview.stop()
        self.camera = cam
        if hasattr(self, "camera_title"):
            self.camera_title.set_text(cam.card)
            self.camera_subtitle.set_text("Connected · Changes apply instantly")
            self.set_title(f"Logioki — {cam.card}")
        self.camera_settings = store.camera_entry(self.settings, cam)
        saved = self.camera_settings.get("controls", {})
        if saved:
            result = store.apply_to_camera(cam, saved)
            self._notify_restore("Restored settings", result)
        self._build_rows()
        self._flush_save()
        self.preview.start(cam.path)

    def _on_device_changed(self, combo, _pspec):
        position = combo.get_selected()
        if 0 <= position < len(self.cameras):
            self._select_camera(self.cameras[position])

    def _on_close(self, _win):
        self._closed = True
        try:
            self._flush_control_writes()
            if self._save_timeout:
                GLib.source_remove(self._save_timeout)
                self._save_timeout = 0
            self._flush_save(wait=True)
        except Exception:
            # Closing must still release the preview and every device if the
            # final persistence attempt fails.
            LOGGER.exception("Could not persist settings while closing")
        finally:
            try:
                self.preview.stop()
            except Exception:
                LOGGER.exception("Could not stop the camera preview")
            try:
                self._save_executor.shutdown(wait=True, cancel_futures=False)
            except Exception:
                LOGGER.exception("Could not stop the settings worker")
            for cam in self.cameras:
                try:
                    cam.close()
                except OSError:
                    LOGGER.exception("Could not close camera %s", cam.path)
        return False

    # ---------- camera <-> UI sync ----------

    def _sync_from_camera(self, values=None):
        """Read current values + inactive flags from the device into the UI."""
        self._updating = True
        try:
            cam = self.camera
            cam.refresh_flags()
            for ctrl in cam.controls:
                row, widget = self.rows.get(ctrl.id, (None, None))
                if row is None:
                    continue
                try:
                    value = (
                        values[str(ctrl.id)]
                        if values is not None and str(ctrl.id) in values
                        else cam.get(ctrl.id)
                    )
                except (KeyError, OSError):
                    row.set_sensitive(False)
                    continue
                if ctrl.type == v4l2ctl.TYPE_BOOL:
                    widget.set_active(bool(value))
                elif ctrl.type == v4l2ctl.TYPE_MENU:
                    for pos, (idx, _label) in enumerate(ctrl.menu_items):
                        if idx == value:
                            widget.set_selected(pos)
                            break
                else:
                    widget.set_value(value)
                row.set_sensitive(not ctrl.inactive and not ctrl.read_only)
        finally:
            self._updating = False

    def _apply(self, ctrl, value, resync=False):
        if self._updating:
            return
        try:
            self.camera.set(ctrl.id, value)
            actual = self.camera.get(ctrl.id)
        except OSError as e:
            self._notify(f"{ctrl.name}: {e.strerror}")
            return
        if actual != value:
            self._notify(f"{ctrl.name}: requested {value}, camera reports {actual}")
            self._sync_from_camera()
            return
        self.camera_settings.setdefault("controls", {})[str(ctrl.id)] = actual
        self._schedule_save()
        if resync:
            # Mode switches can gate or rewrite other controls.
            values = store.capture_controls(self.camera)
            self.camera_settings["controls"] = values
            self._sync_from_camera(values)

    def _queue_control_write(self, ctrl, value):
        if self._updating:
            return
        self._pending_controls[ctrl.id] = (ctrl, value)
        if not self._control_timeout:
            self._control_timeout = GLib.timeout_add(35, self._on_control_timeout)

    def _on_control_timeout(self):
        self._control_timeout = 0
        return self._flush_control_writes()

    def _flush_control_writes(self):
        if self._control_timeout:
            GLib.source_remove(self._control_timeout)
            self._control_timeout = 0
        pending = list(self._pending_controls.values())
        self._pending_controls.clear()
        for ctrl, value in pending:
            self._apply(ctrl, value)
        return GLib.SOURCE_REMOVE

    def _on_scale_changed(self, scale, ctrl):
        self._queue_control_write(ctrl, int(scale.get_value()))

    def _on_bool_changed(self, row, _pspec, ctrl):
        self._flush_control_writes()
        self._apply(ctrl, int(row.get_active()), resync=True)

    def _on_menu_changed(self, row, _pspec, ctrl):
        self._flush_control_writes()
        pos = row.get_selected()
        if 0 <= pos < len(ctrl.menu_items):
            self._apply(ctrl, ctrl.menu_items[pos][0], resync=True)

    def _menu_model(self, ctrl):
        return Gtk.StringList.new([label for _value, label in ctrl.menu_items])

    def _numeric_control(self, ctrl):
        adjustment = Gtk.Adjustment(
            lower=ctrl.minimum,
            upper=ctrl.maximum,
            step_increment=ctrl.step,
            page_increment=ctrl.step * 10,
        )
        scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=adjustment,
            draw_value=False,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        scale.set_digits(0)
        scale.connect("value-changed", self._on_scale_changed, ctrl)
        spin = Gtk.SpinButton(adjustment=adjustment, digits=0, numeric=True)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.append(scale)
        controls.append(spin)
        return scale, controls

    def _on_reset(self, _button):
        self._flush_control_writes()
        defaults = self.camera_settings["presets"]["default"]["controls"]
        result = store.apply_to_camera(self.camera, defaults)
        values = store.capture_controls(self.camera)
        self.camera_settings["controls"] = values
        self._flush_save()
        self._sync_from_camera(values)
        self._select_preset_in_picker("default")
        self._notify_restore("Reset to camera defaults", result)

    # ---------- presets ----------

    def _refresh_preset_picker(self, selected_id=None):
        items = store.preset_items(self.camera_settings)
        self._preset_ids = [preset_id for preset_id, _name in items]
        was_updating = self._updating
        self._updating = True
        self.preset_picker.set_model(Gtk.StringList.new([name for _id, name in items]))
        if selected_id in self._preset_ids:
            self.preset_picker.set_selected(self._preset_ids.index(selected_id))
        elif self._preset_ids:
            self.preset_picker.set_selected(0)
        self._updating = was_updating
        self._update_preset_buttons()

    def _selected_preset(self):
        position = self.preset_picker.get_selected()
        if 0 <= position < len(self._preset_ids):
            return self._preset_ids[position]
        return None

    def _select_preset_in_picker(self, preset_id):
        if preset_id not in self._preset_ids:
            return
        was_updating = self._updating
        self._updating = True
        self.preset_picker.set_selected(self._preset_ids.index(preset_id))
        self._updating = was_updating
        self._update_preset_buttons()

    def _update_preset_buttons(self):
        preset_id = self._selected_preset()
        if hasattr(self, "save_preset_button"):
            self.save_preset_button.set_sensitive(bool(preset_id and preset_id != "default"))
        if hasattr(self, "delete_preset_button"):
            preset = self.camera_settings.get("presets", {}).get(preset_id, {})
            self.delete_preset_button.set_sensitive(bool(preset and not preset.get("builtin")))

    def _on_preset_changed(self, _picker, _pspec):
        if self._updating:
            return
        self._flush_control_writes()
        preset_id = self._selected_preset()
        preset = self.camera_settings.get("presets", {}).get(preset_id)
        if not preset:
            return
        result = store.apply_to_camera(self.camera, preset["controls"])
        values = store.capture_controls(self.camera)
        self.camera_settings["controls"] = values
        self.camera_settings["selected_preset"] = preset_id
        self._flush_save()
        self._sync_from_camera(values)
        self._update_preset_buttons()
        self._notify_restore(f"Applied {preset['name']}", result)

    def _on_save_preset(self, _button):
        self._flush_control_writes()
        preset_id = self._selected_preset()
        values = store.capture_controls(self.camera)
        try:
            store.update_preset(self.camera_settings, preset_id, values)
        except (KeyError, ValueError) as exc:
            self._notify(str(exc))
            return
        self.camera_settings["controls"] = values
        self._flush_save()
        self._notify(f"Saved {self.camera_settings['presets'][preset_id]['name']}")

    def _on_new_preset(self, _button):
        dialog = Gtk.Window(title="New Preset", transient_for=self, modal=True)
        dialog.set_default_size(360, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_spacing(12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        entry = Gtk.Entry(placeholder_text="Preset name", activates_default=True)
        box.append(entry)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        create = Gtk.Button(label="Create")
        create.add_css_class("suggested-action")
        create.set_receives_default(True)
        cancel.connect("clicked", lambda _button: dialog.destroy())
        create.connect("clicked", lambda _button: self._on_new_preset_response(dialog, entry))
        entry.connect("activate", lambda _entry: self._on_new_preset_response(dialog, entry))
        actions.append(cancel)
        actions.append(create)
        box.append(actions)
        dialog.set_child(box)
        dialog.set_default_widget(create)
        dialog.present()
        entry.grab_focus()

    def _on_new_preset_response(self, dialog, entry):
        self._flush_control_writes()
        try:
            preset_id = store.create_preset(
                self.camera_settings,
                entry.get_text(),
                store.capture_controls(self.camera),
            )
        except ValueError as exc:
            self._notify(str(exc))
            entry.grab_focus()
            return
        self.camera_settings["selected_preset"] = preset_id
        self._flush_save()
        self._refresh_preset_picker(preset_id)
        self._notify(f"Created {self.camera_settings['presets'][preset_id]['name']}")
        dialog.destroy()

    def _on_delete_preset(self, _button):
        self._flush_control_writes()
        preset_id = self._selected_preset()
        try:
            name = self.camera_settings["presets"][preset_id]["name"]
            store.delete_preset(self.camera_settings, preset_id)
        except (KeyError, ValueError) as exc:
            self._notify(str(exc))
            return
        defaults = self.camera_settings["presets"]["default"]
        result = store.apply_to_camera(self.camera, defaults["controls"])
        values = store.capture_controls(self.camera)
        self.camera_settings["controls"] = values
        self.camera_settings["selected_preset"] = "default"
        self._refresh_preset_picker("default")
        self._flush_save()
        self._sync_from_camera(values)
        self._notify_restore(f"Deleted {name}; applied Default", result)

    def _notify_restore(self, action, result):
        message = f"{action}: {len(result.applied)} applied"
        if result.skipped:
            message += f", {len(result.skipped)} inactive/unavailable"
        if result.failed:
            control_names = {str(ctrl.id): ctrl.name for ctrl in self.camera.controls}
            details = "; ".join(
                f"{control_names.get(ctrl_id, ctrl_id)}: {reason}"
                for ctrl_id, reason in result.failed.items()
            )
            message += f", {len(result.failed)} failed ({details})"
        self._notify(message)

    # ---------- persistence ----------

    def _schedule_save(self):
        if self._save_timeout:
            GLib.source_remove(self._save_timeout)
        self._save_timeout = GLib.timeout_add(400, self._flush_save)

    def _flush_save(self, wait=False):
        self._save_timeout = 0
        for cam in self.cameras:
            entry = self.settings.get("cameras", {}).get(cam.key)
            if entry is not None:
                entry["device"] = cam.path
        future = self._save_executor.submit(store.save, copy.deepcopy(self.settings))
        if wait:
            future.result(timeout=10)
        else:
            future.add_done_callback(self._on_save_finished)
        return GLib.SOURCE_REMOVE

    def _on_save_finished(self, future):
        try:
            future.result()
        except Exception as exc:
            LOGGER.exception("Could not save settings")
            if not self._closed:
                GLib.idle_add(self._notify, f"Could not save settings: {exc}")

    # ---------- autostart ----------

    def _autostart_enabled(self):
        desired = self.settings.setdefault("app", {}).get("auto_restore", False)
        return bool(desired and service.SYSTEMD_UNIT.exists())

    def _run_service_task(self, task, callback):
        if self._service_busy:
            return False
        self._service_busy = True

        def worker():
            try:
                result = task()
            except Exception as exc:
                result = (False, str(exc))
            GLib.idle_add(callback, *result)

        threading.Thread(target=worker, name="logioki-systemd", daemon=True).start()
        return True

    def _ensure_autostart(self):
        def ensure():
            if service.is_restore_service_enabled():
                return True, None
            return service.install_restore_service()

        self._run_service_task(
            ensure,
            lambda ok, error: self._finish_autostart_change(True, ok, error, False),
        )
        return GLib.SOURCE_REMOVE

    def _on_autostart_toggled(self, row, _pspec):
        if self._updating:
            return
        enabled = row.get_active()
        row.set_sensitive(False)
        task = service.install_restore_service if enabled else service.remove_restore_service
        started = self._run_service_task(
            task,
            lambda ok, error: self._finish_autostart_change(enabled, ok, error, True),
        )
        if not started:
            self._updating = True
            row.set_active(not enabled)
            row.set_sensitive(True)
            self._updating = False

    def _finish_autostart_change(self, enabled, ok, error, announce):
        self._service_busy = False
        if self._closed:
            return GLib.SOURCE_REMOVE
        if hasattr(self, "autostart_row"):
            self._updating = True
            self.autostart_row.set_active(enabled if ok else not enabled)
            self.autostart_row.set_sensitive(True)
            self._updating = False
        if ok:
            self.settings.setdefault("app", {})["auto_restore"] = enabled
            self._flush_save()
            if announce:
                message = (
                    "Settings will be restored at every login"
                    if enabled
                    else "Automatic login restore disabled"
                )
                self._notify(message)
        else:
            action = "enable" if enabled else "disable"
            self._notify(f"Could not {action} automatic restore: {error}")
        return GLib.SOURCE_REMOVE


if Adw is not None:

    class GnomeWindow(WindowController, Adw.ApplicationWindow):
        def __init__(self, app):
            Adw.ApplicationWindow.__init__(
                self,
                application=app,
                title="Logioki",
                default_width=760,
                default_height=860,
            )
            self._init_controller()

            toolbar = Adw.ToolbarView()
            header = Adw.HeaderBar()
            toolbar.add_top_bar(header)
            self.set_content(toolbar)

            if len(self.cameras) > 1:
                names = Gtk.StringList.new(camera_labels(self.cameras))
                self.device_combo = Gtk.DropDown(model=names)
                self.device_combo.connect("notify::selected", self._on_device_changed)
                header.pack_start(self.device_combo)

            reset = Gtk.Button(
                icon_name="edit-undo-symbolic",
                tooltip_text="Reset all controls to camera defaults",
            )
            _set_accessible_label(reset, "Reset all controls to camera defaults")
            reset.set_sensitive(bool(self.cameras))
            reset.connect("clicked", self._on_reset)
            header.pack_end(reset)

            self.toast_overlay = Adw.ToastOverlay()
            toolbar.set_content(self.toast_overlay)

            scroll = Gtk.ScrolledWindow(vexpand=True)
            self.toast_overlay.set_child(scroll)
            clamp = Adw.Clamp(
                maximum_size=680,
                margin_top=18,
                margin_bottom=24,
                margin_start=12,
                margin_end=12,
            )
            scroll.set_child(clamp)

            self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            clamp.set_child(self.page_box)

            self.preview = Preview(on_error=self._notify)
            self.preview.set_size_request(-1, 360)
            self.page_box.append(self.preview)

            self.groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            self.page_box.append(self.groups_box)

            self._select_initial_camera()

        # ---------- UI construction ----------

        def _build_rows(self):
            self._updating = True
            while child := self.groups_box.get_first_child():
                self.groups_box.remove(child)
            self.rows = {}
            cam = self.camera

            presets = Adw.PreferencesGroup(title="Image Presets")
            preset_row = Adw.ActionRow(
                title="Preset",
                subtitle="Apply a saved group of camera settings",
            )
            self.preset_picker = Gtk.DropDown(valign=Gtk.Align.CENTER)
            self.preset_picker.set_size_request(150, -1)
            self.preset_picker.connect("notify::selected", self._on_preset_changed)
            preset_row.add_suffix(self.preset_picker)
            presets.add(preset_row)

            actions = Adw.ActionRow(title="Manage presets")
            action_box = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE,
                column_spacing=6,
                row_spacing=6,
                min_children_per_line=1,
                max_children_per_line=3,
                homogeneous=True,
            )
            self.save_preset_button = Gtk.Button(label="Save Current")
            self.save_preset_button.connect("clicked", self._on_save_preset)
            new_button = Gtk.Button(label="New…")
            new_button.connect("clicked", self._on_new_preset)
            self.delete_preset_button = Gtk.Button(
                icon_name="user-trash-symbolic", tooltip_text="Delete custom preset"
            )
            _set_accessible_label(self.delete_preset_button, "Delete custom preset")
            self.delete_preset_button.connect("clicked", self._on_delete_preset)
            action_box.insert(self.save_preset_button, -1)
            action_box.insert(new_button, -1)
            action_box.insert(self.delete_preset_button, -1)
            actions.add_suffix(action_box)
            presets.add(actions)
            self.groups_box.append(presets)
            self._refresh_preset_picker(self.camera_settings.get("selected_preset", "default"))

            titles = {"User Controls": "Image", "Camera Controls": "Camera"}
            for group_name, controls in cam.groups.items():
                group = Adw.PreferencesGroup(title=titles.get(group_name, group_name))
                for ctrl in controls:
                    row = self._make_row(ctrl)
                    if row:
                        group.add(row)
                self.groups_box.append(group)

            startup = Adw.PreferencesGroup(title="Startup")
            self.autostart_row = Adw.SwitchRow(
                title="Apply at login",
                subtitle="Restore these settings after reboot, even if Logioki "
                "isn't opened (systemd user service)",
            )
            self.autostart_row.set_active(self._autostart_enabled())
            self.autostart_row.connect("notify::active", self._on_autostart_toggled)
            startup.add(self.autostart_row)
            self.groups_box.append(startup)

            self._sync_from_camera()

        def _make_row(self, ctrl):
            if ctrl.type == v4l2ctl.TYPE_BOOL:
                row = Adw.SwitchRow(title=ctrl.name)
                _set_accessible_label(row, ctrl.name)
                row.connect("notify::active", self._on_bool_changed, ctrl)
                self.rows[ctrl.id] = (row, row)
                return row

            if ctrl.type == v4l2ctl.TYPE_MENU:
                row = Adw.ComboRow(title=ctrl.name, model=self._menu_model(ctrl))
                _set_accessible_label(row, ctrl.name)
                row.connect("notify::selected", self._on_menu_changed, ctrl)
                self.rows[ctrl.id] = (row, row)
                return row

            if ctrl.type == v4l2ctl.TYPE_INT:
                row = Adw.ActionRow(title=ctrl.name)
                scale, controls = self._numeric_control(ctrl)
                _set_accessible_label(scale, ctrl.name)
                row.add_suffix(controls)
                self.rows[ctrl.id] = (row, scale)
                return row

            return None

        def _show_no_camera(self):
            status = Adw.StatusPage(
                title="No camera found",
                description="Connect a UVC webcam and reopen.",
                icon_name="camera-disabled-symbolic",
            )
            self.toast_overlay.set_child(status)

        def _notify(self, message):
            self.toast_overlay.add_toast(Adw.Toast(title=message))


class KdeWindow(WindowController, Gtk.ApplicationWindow):
    def __init__(self, app):
        Gtk.ApplicationWindow.__init__(
            self,
            application=app,
            title="Logioki",
            default_width=960,
            default_height=700,
        )
        self._init_controller()
        self._notification_timeout = 0

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.camera_title = Gtk.Label(label="Logioki")
        self.camera_title.add_css_class("kde-header-title")
        self.camera_subtitle = Gtk.Label(label="Camera control center")
        self.camera_subtitle.add_css_class("kde-header-subtitle")
        title_box.append(self.camera_title)
        title_box.append(self.camera_subtitle)
        header.set_title_widget(title_box)

        if len(self.cameras) > 1:
            names = Gtk.StringList.new(camera_labels(self.cameras))
            self.device_combo = Gtk.DropDown(model=names)
            self.device_combo.set_tooltip_text("Choose a camera")
            self.device_combo.connect("notify::selected", self._on_device_changed)
            header.pack_start(self.device_combo)

        reset = Gtk.Button(
            icon_name="edit-undo-symbolic",
            tooltip_text="Reset camera to factory defaults",
        )
        _set_accessible_label(reset, "Reset all controls to camera defaults")
        reset.set_sensitive(bool(self.cameras))
        reset.connect("clicked", self._on_reset)
        header.pack_end(reset)

        root = Gtk.Overlay()
        root.add_css_class("kde-root")
        self.set_child(root)

        self.content_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True)
        root.set_child(self.content_holder)

        self.notification_revealer = Gtk.Revealer()
        self.notification_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.notification_revealer.set_valign(Gtk.Align.END)
        self.notification_revealer.set_halign(Gtk.Align.CENTER)
        self.notification_label = Gtk.Label(wrap=True, max_width_chars=72)
        self.notification_label.add_css_class("kde-notification")
        self.notification_revealer.set_child(self.notification_label)
        root.add_overlay(self.notification_revealer)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_position(610)
        split.set_resize_start_child(True)
        split.set_shrink_start_child(True)
        split.set_resize_end_child(True)
        split.set_shrink_end_child(True)
        self.content_holder.append(split)

        preview_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        preview_pane.add_css_class("kde-preview-pane")
        heading = Gtk.Label(label="Live preview", xalign=0)
        heading.add_css_class("kde-preview-heading")
        description = Gtk.Label(
            label="See every adjustment instantly before using the camera elsewhere.",
            xalign=0,
            wrap=True,
        )
        description.add_css_class("kde-preview-subtitle")
        preview_pane.append(heading)
        preview_pane.append(description)

        preview_frame = Gtk.AspectFrame(
            ratio=16 / 9,
            obey_child=False,
            xalign=0.5,
            yalign=0.5,
            hexpand=True,
            vexpand=True,
        )
        preview_frame.add_css_class("kde-preview-frame")
        preview_frame.set_overflow(Gtk.Overflow.HIDDEN)
        preview_overlay = Gtk.Overlay()

        self.preview = Preview(on_error=self._notify)
        self.preview.add_css_class("kde-preview")
        preview_overlay.set_child(self.preview)
        live_badge = Gtk.Label(label="●  LIVE", halign=Gtk.Align.START, valign=Gtk.Align.START)
        live_badge.add_css_class("kde-live-badge")
        preview_overlay.add_overlay(live_badge)
        preview_frame.set_child(preview_overlay)
        preview_pane.append(preview_frame)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.add_css_class("kde-preview-footer")
        footer.append(Gtk.Image(icon_name="dialog-information-symbolic"))
        hint = Gtk.Label(
            label="Settings remain active after Logioki closes, until the camera loses power.",
            xalign=0,
            wrap=True,
            hexpand=True,
        )
        hint.add_css_class("kde-hint")
        footer.append(hint)
        preview_pane.append(footer)
        split.set_start_child(preview_pane)

        inspector = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inspector.add_css_class("kde-inspector")
        inspector.set_size_request(330, -1)
        switcher_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        switcher_bar.add_css_class("kde-tabbar")
        self.page_picker = Gtk.DropDown(
            model=Gtk.StringList.new(["Presets", "Image", "Camera", "Startup"]),
            hexpand=True,
        )
        _set_accessible_label(self.page_picker, "Settings page")
        self.page_picker.connect("notify::selected", self._on_settings_page_changed)
        switcher_bar.append(self.page_picker)
        inspector.append(switcher_bar)

        self.settings_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=160,
            vexpand=True,
        )
        inspector.append(self.settings_stack)
        split.set_end_child(inspector)

        self._select_initial_camera()

    # ---------- UI construction ----------

    def _build_rows(self):
        self._updating = True
        while child := self.settings_stack.get_first_child():
            self.settings_stack.remove(child)
        self.rows = {}
        cam = self.camera

        preset_page, preset_content = self._make_page(
            "Image presets",
            "Switch your whole camera setup in one click, or save the current look.",
        )
        preset_hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        preset_hero.add_css_class("kde-preset-hero")
        preset_name = Gtk.Label(label="Active preset", xalign=0)
        preset_name.add_css_class("kde-preset-name")
        preset_hero.append(preset_name)
        self.preset_picker = Gtk.DropDown(hexpand=True)
        self.preset_picker.connect("notify::selected", self._on_preset_changed)
        preset_hero.append(self.preset_picker)
        preset_content.append(preset_hero)

        action_box = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=8,
            row_spacing=8,
            min_children_per_line=1,
            max_children_per_line=3,
            homogeneous=True,
        )
        new_button = Gtk.Button(label="New preset…")
        new_button.connect("clicked", self._on_new_preset)
        self.save_preset_button = Gtk.Button(label="Save changes")
        self.save_preset_button.add_css_class("suggested-action")
        self.save_preset_button.connect("clicked", self._on_save_preset)
        self.delete_preset_button = Gtk.Button(
            icon_name="edit-delete-symbolic", tooltip_text="Delete this custom preset"
        )
        _set_accessible_label(self.delete_preset_button, "Delete custom preset")
        self.delete_preset_button.add_css_class("flat")
        self.delete_preset_button.connect("clicked", self._on_delete_preset)
        action_box.insert(new_button, -1)
        action_box.insert(self.save_preset_button, -1)
        action_box.insert(self.delete_preset_button, -1)
        preset_content.append(action_box)
        self.settings_stack.add_titled(preset_page, "presets", "Presets")
        self._refresh_preset_picker(self.camera_settings.get("selected_preset", "streaming"))

        image_page, image_content = self._make_page(
            "Image",
            "Tune color, clarity, white balance, and other picture characteristics.",
        )
        camera_page, camera_content = self._make_page(
            "Camera",
            "Control exposure, framing, focus, zoom, and camera behavior.",
        )
        titles = {"User Controls": "Image", "Camera Controls": "Camera"}
        for group_name, controls in cam.groups.items():
            group, rows = self._make_group(titles.get(group_name, group_name))
            for ctrl in controls:
                row = self._make_row(ctrl)
                if row:
                    rows.append(row)
            target = camera_content if "camera" in group_name.casefold() else image_content
            target.append(group)
        self.settings_stack.add_titled(image_page, "image", "Image")
        self.settings_stack.add_titled(camera_page, "camera", "Camera")

        startup_page, startup_content = self._make_page(
            "Startup",
            "Keep your preferred look after login without leaving Logioki open.",
        )
        group, rows = self._make_group("Restore settings")
        row, switch = self._make_text_switch_row(
            "Apply at login",
            "Wait for the webcam and restore the last settings automatically.",
            self._on_autostart_toggled,
        )
        switch.set_active(self._autostart_enabled())
        self.autostart_row = switch
        rows.append(row)
        startup_content.append(group)
        self.settings_stack.add_titled(startup_page, "startup", "Startup")

        self._sync_from_camera()

    def _on_settings_page_changed(self, picker, _pspec):
        page_names = ("presets", "image", "camera", "startup")
        position = picker.get_selected()
        if 0 <= position < len(page_names):
            self.settings_stack.set_visible_child_name(page_names[position])

    def _make_page(self, title, description):
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vexpand=True,
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.add_css_class("kde-page")
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("kde-page-heading")
        subtitle = Gtk.Label(label=description, xalign=0, wrap=True)
        subtitle.add_css_class("kde-page-description")
        content.append(heading)
        content.append(subtitle)
        scroll.set_child(content)
        return scroll, content

    def _make_group(self, title):
        group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        group.add_css_class("kde-group")

        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("kde-group-title")
        group.append(label)

        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        group.append(rows)
        return group, rows

    def _make_row(self, ctrl):
        if ctrl.type == v4l2ctl.TYPE_BOOL:
            row, switch = self._make_text_switch_row(
                ctrl.name, self._control_hint(ctrl.name), self._on_bool_changed, ctrl
            )
            self.rows[ctrl.id] = (row, switch)
            _set_accessible_label(switch, ctrl.name)
            return row

        if ctrl.type == v4l2ctl.TYPE_MENU:
            row = self._make_row_box()
            text = self._make_row_text(ctrl.name, self._control_hint(ctrl.name))
            dropdown = Gtk.DropDown(model=self._menu_model(ctrl), valign=Gtk.Align.CENTER)
            dropdown.set_size_request(120, -1)
            dropdown.connect("notify::selected", self._on_menu_changed, ctrl)
            _set_accessible_label(dropdown, ctrl.name)
            row.append(text)
            row.append(dropdown)
            self.rows[ctrl.id] = (row, dropdown)
            return row

        if ctrl.type == v4l2ctl.TYPE_INT:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            row.add_css_class("kde-row")
            row.append(self._make_row_text(ctrl.name, self._control_hint(ctrl.name)))
            scale, controls = self._numeric_control(ctrl)
            _set_accessible_label(scale, ctrl.name)
            row.append(controls)
            self.rows[ctrl.id] = (row, scale)
            return row

        return None

    def _make_text_switch_row(self, title, subtitle, callback, *callback_args):
        row = self._make_row_box()
        text = self._make_row_text(title, subtitle)
        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        switch.connect("notify::active", callback, *callback_args)
        row.append(text)
        row.append(switch)
        return row, switch

    def _make_row_box(self):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("kde-row")
        row.set_valign(Gtk.Align.CENTER)
        return row

    def _make_title_label(self, title):
        label = Gtk.Label(label=title, xalign=0, wrap=True, hexpand=True)
        label.add_css_class("kde-row-title")
        label.set_max_width_chars(32)
        return label

    def _make_row_text(self, title, subtitle=None):
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        text.append(self._make_title_label(title))
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            sub.add_css_class("kde-row-subtitle")
            text.append(sub)
        return text

    def _control_hint(self, name):
        hints = {
            "brightness": "Adjust the overall light level.",
            "contrast": "Increase or soften the separation between tones.",
            "saturation": "Control the intensity of colors.",
            "sharpness": "Add or reduce fine edge detail.",
            "white balance temperature": "Shift the image warmer or cooler.",
            "white balance, automatic": "Let the camera balance color temperature.",
            "auto white balance": "Let the camera balance color temperature.",
            "exposure time, absolute": "Balance brightness against motion blur.",
            "exposure, auto": "Let the camera adapt exposure to the scene.",
            "gain": "Brighten the sensor signal; high values may add noise.",
            "focus, automatic continuous": "Keep the subject in focus automatically.",
            "focus (absolute)": "Set focus distance manually.",
            "zoom, absolute": "Crop closer while keeping a global camera setting.",
            "power line frequency": "Reduce lighting flicker for your local power grid.",
        }
        return hints.get(name.casefold())

    def _show_no_camera(self):
        while child := self.content_holder.get_first_child():
            self.content_holder.remove(child)

        status = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            vexpand=True,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        icon = Gtk.Image(icon_name="camera-disabled-symbolic", pixel_size=64)
        title = Gtk.Label(label="No camera found")
        title.add_css_class("title-2")
        description = Gtk.Label(label="Connect a UVC webcam and reopen.")
        status.append(icon)
        status.append(title)
        status.append(description)
        self.content_holder.append(status)

    def _notify(self, message):
        if self._notification_timeout:
            GLib.source_remove(self._notification_timeout)
        self.notification_label.set_text(message)
        self.notification_revealer.set_reveal_child(True)
        self._notification_timeout = GLib.timeout_add_seconds(4, self._hide_notification)

    def _hide_notification(self):
        self._notification_timeout = 0
        self.notification_revealer.set_reveal_child(False)
        return GLib.SOURCE_REMOVE


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
