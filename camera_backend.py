"""Toolkit-neutral camera discovery service."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import v4l2ctl
from device_monitor import DeviceRegistry
from models import CameraDevice


class CameraBackend:
    def __init__(self, discover: Callable[[], Iterable[CameraDevice]] | None = None):
        self._discover = discover or v4l2ctl.list_cameras

    def discover(self) -> list[CameraDevice]:
        return list(self._discover())

    def registry(self, initial=()) -> DeviceRegistry:
        return DeviceRegistry(self.discover, initial)
