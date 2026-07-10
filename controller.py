"""Shared GTK window controller and camera lifecycle orchestration."""

from __future__ import annotations

import copy
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

import service  # noqa: E402
import store  # noqa: E402
import v4l2ctl  # noqa: E402
from device_monitor import DeviceRegistry  # noqa: E402

LOGGER = logging.getLogger(__name__)


def camera_labels(cameras):
    counts = {}
    for camera in cameras:
        counts[camera.card] = counts.get(camera.card, 0) + 1
    return [
        f"{camera.card} — {camera.identity_label}" if counts[camera.card] > 1 else camera.card
        for camera in cameras
    ]


class WindowController:
    def _init_controller(self):
        self.settings = store.load()
        self.cameras = v4l2ctl.list_cameras()
        self._device_registry = DeviceRegistry(v4l2ctl.list_cameras, self.cameras)
        self._device_monitor = None
        self._device_refresh_timeout = 0
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
        self._start_device_monitor()

    # ---------- camera lifecycle ----------

    def _select_camera(self, cam):
        self._flush_control_writes()
        self.preview.stop()
        self.camera = cam
        self._show_camera_content()
        if hasattr(self, "reset_button"):
            self.reset_button.set_sensitive(True)
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
        if self._updating:
            return
        position = combo.get_selected()
        if 0 <= position < len(self.cameras):
            self._select_camera(self.cameras[position])

    def _start_device_monitor(self):
        try:
            self._device_monitor = Gio.File.new_for_path("/dev").monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self._device_monitor.connect("changed", self._on_device_event)
        except GLib.Error:
            LOGGER.exception("Could not monitor camera device changes")

    def _on_device_event(self, _monitor, file, other_file, _event_type):
        names = (file.get_basename(), other_file.get_basename() if other_file else None)
        if not any(name and name.startswith("video") and name[5:].isdigit() for name in names):
            return
        if self._device_refresh_timeout:
            GLib.source_remove(self._device_refresh_timeout)
        self._device_refresh_timeout = GLib.timeout_add(300, self._refresh_devices)

    def _refresh_devices(self):
        self._device_refresh_timeout = 0
        try:
            change = self._device_registry.refresh()
        except OSError as exc:
            LOGGER.exception("Could not refresh camera devices")
            self._notify(f"Could not refresh cameras: {exc}")
            return GLib.SOURCE_REMOVE

        previous_key = self.camera.key if self.camera is not None else None
        self.cameras = list(change.devices)
        self._update_device_picker(previous_key)
        available_keys = {camera.key for camera in self.cameras}
        if previous_key not in available_keys:
            self.preview.stop()
            self.camera = None
            self.camera_settings = None
            for removed in change.removed:
                try:
                    removed.close()
                except OSError:
                    LOGGER.exception("Could not close disconnected camera %s", removed.path)
            if self.cameras:
                self._select_camera(self.cameras[0])
                self._notify("Camera connected")
            else:
                if hasattr(self, "reset_button"):
                    self.reset_button.set_sensitive(False)
                self._show_no_camera()
                self._notify("Camera disconnected")
        else:
            for removed in change.removed:
                try:
                    removed.close()
                except OSError:
                    LOGGER.exception("Could not close disconnected camera %s", removed.path)
            if change.added:
                self._notify("Camera connected")
        return GLib.SOURCE_REMOVE

    def _update_device_picker(self, selected_key=None):
        if not hasattr(self, "device_combo"):
            return
        was_updating, self._updating = self._updating, True
        try:
            self.device_combo.set_model(Gtk.StringList.new(camera_labels(self.cameras)))
            self.device_combo.set_visible(len(self.cameras) > 1)
            keys = [camera.key for camera in self.cameras]
            if selected_key in keys:
                self.device_combo.set_selected(keys.index(selected_key))
            elif keys:
                self.device_combo.set_selected(0)
        finally:
            self._updating = was_updating

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
            if self._device_refresh_timeout:
                GLib.source_remove(self._device_refresh_timeout)
                self._device_refresh_timeout = 0
            if self._device_monitor is not None:
                self._device_monitor.cancel()
                self._device_monitor = None
            try:
                self.preview.stop()
            except Exception:
                LOGGER.exception("Could not stop the camera preview")
            try:
                self._save_executor.shutdown(wait=True, cancel_futures=False)
            except Exception:
                LOGGER.exception("Could not stop the settings worker")
            for cam in self._device_registry.devices:
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
