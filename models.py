"""Typed domain contracts shared by frontends and camera backends."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypedDict


@dataclass(frozen=True, slots=True)
class CameraListItem:
    label: str
    key: str


@dataclass(frozen=True, slots=True)
class ControlListItem:
    controlId: str
    name: str
    kind: str
    group: str
    showGroup: bool
    value: int
    minimum: int
    maximum: int
    step: int
    available: bool
    reason: str
    menuItems: list[dict[str, int | str]]


@dataclass(frozen=True, slots=True)
class PresetListItem:
    presetId: str
    name: str
    builtin: bool
    editable: bool


@dataclass(frozen=True, slots=True)
class ErrorListItem:
    message: str


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
    driver: str
    bus_info: str
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
    open_at_login: bool


class SettingsData(TypedDict):
    version: int
    app: ApplicationSettings
    cameras: dict[str, CameraSettings]
    legacy_cameras: dict[str, CameraSettings]
