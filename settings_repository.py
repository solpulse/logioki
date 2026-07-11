"""Persistence boundary used by the application view model."""

from __future__ import annotations

from collections.abc import Mapping

import store


class SettingsRepository:
    def empty(self):
        return store._empty_data()

    def load(self):
        return store.load()

    def save(self, settings) -> None:
        store.save(settings)

    def camera_entry(self, settings, camera):
        return store.camera_entry(settings, camera)

    def apply(self, camera, controls: Mapping[str, int]):
        return store.apply_to_camera(camera, controls)

    def empty_restore_result(self):
        return store.RestoreResult()

    def capture(self, camera, include_read_only=False):
        return store.capture_controls(camera, include_read_only=include_read_only)

    def preset_items(self, entry):
        return store.preset_items(entry)

    def create_preset(self, entry, name, controls):
        return store.create_preset(entry, name, controls)

    def update_preset(self, entry, preset_id, controls) -> None:
        store.update_preset(entry, preset_id, controls)

    def delete_preset(self, entry, preset_id) -> None:
        store.delete_preset(entry, preset_id)
