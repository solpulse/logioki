"""GNOME/libadwaita presentation for Logioki."""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

import v4l2ctl  # noqa: E402
from controller import WindowController, camera_labels  # noqa: E402
from preview import Preview  # noqa: E402


def _set_accessible_label(widget, label):
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


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

        names = Gtk.StringList.new(camera_labels(self.cameras))
        self.device_combo = Gtk.DropDown(model=names)
        self.device_combo.set_visible(len(self.cameras) > 1)
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
        self.reset_button = reset

        self.toast_overlay = Adw.ToastOverlay()
        toolbar.set_content(self.toast_overlay)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.toast_overlay.set_child(scroll)
        self.camera_content = scroll
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
            description="Connect a UVC webcam. Logioki will detect it automatically.",
            icon_name="camera-disabled-symbolic",
        )
        self.toast_overlay.set_child(status)

    def _show_camera_content(self):
        self.toast_overlay.set_child(self.camera_content)

    def _notify(self, message):
        self.toast_overlay.add_toast(Adw.Toast(title=message))
