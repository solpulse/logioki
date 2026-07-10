"""Typed domain contracts shared by frontends and camera backends."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, TypedDict


class ControlDescriptor(Protocol):
    id: int
    name: str
    type: int
    minimum: int
    maximum: int
    step: int
    default: int
    inactive: bool
    read_only: bool
    menu_items: list[tuple[int, str]]


class CameraDevice(Protocol):
    path: str
    card: str
    key: str
    identity_label: str
    controls: Sequence[ControlDescriptor]
    groups: Mapping[str, Sequence[ControlDescriptor]]

    def get(self, control_id: int) -> int: ...

    def set(self, control_id: int, value: int) -> None: ...

    def refresh_flags(self) -> None: ...

    def close(self) -> None: ...


class PresetSettings(TypedDict):
    name: str
    builtin: bool
    controls: dict[str, int]


class CameraSettings(TypedDict):
    name: str
    device: str
    controls: dict[str, int]
    presets: dict[str, PresetSettings]
    selected_preset: str


class ApplicationSettings(TypedDict):
    auto_restore: bool


class SettingsData(TypedDict):
    version: int
    app: ApplicationSettings
    cameras: dict[str, CameraSettings]
    legacy_cameras: dict[str, CameraSettings]
