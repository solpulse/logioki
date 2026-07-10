"""Plasma-oriented GTK fallback presentation for Logioki."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import v4l2ctl  # noqa: E402
from controller import WindowController, camera_labels  # noqa: E402
from preview import Preview  # noqa: E402


def _set_accessible_label(widget, label):
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


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

        names = Gtk.StringList.new(camera_labels(self.cameras))
        self.device_combo = Gtk.DropDown(model=names)
        self.device_combo.set_visible(len(self.cameras) > 1)
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
        self.reset_button = reset

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
        self.camera_content = split
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
        description = Gtk.Label(label="Connect a UVC webcam. Logioki will detect it automatically.")
        status.append(icon)
        status.append(title)
        status.append(description)
        self.content_holder.append(status)

    def _show_camera_content(self):
        while child := self.content_holder.get_first_child():
            self.content_holder.remove(child)
        self.content_holder.append(self.camera_content)

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
