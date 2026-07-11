"""Camera discovery reconciliation independent of a presentation toolkit."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from models import CameraDevice

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeviceChange:
    devices: tuple[CameraDevice, ...]
    added: tuple[CameraDevice, ...]
    removed: tuple[CameraDevice, ...]


class DeviceRegistry:
    """Own open camera objects and reconcile repeated discovery snapshots."""

    def __init__(
        self,
        discover: Callable[[], Iterable[CameraDevice]],
        initial: Iterable[CameraDevice] = (),
    ) -> None:
        self._discover = discover
        self._devices = []
        seen: set[str] = set()
        for device in initial:
            if device.key in seen:
                try:
                    device.close()
                except OSError:
                    LOGGER.exception("Could not close duplicate camera %s", device.path)
                continue
            seen.add(device.key)
            self._devices.append(device)

    @property
    def devices(self) -> tuple[CameraDevice, ...]:
        return tuple(self._devices)

    def refresh(self) -> DeviceChange:
        discovered = list(self._discover())
        previous = {device.key: device for device in self._devices}
        current: list[CameraDevice] = []
        added: list[CameraDevice] = []
        retired: list[CameraDevice] = []
        seen: set[str] = set()

        for candidate in discovered:
            if candidate.key in seen:
                try:
                    candidate.close()
                except OSError:
                    LOGGER.exception("Could not close duplicate camera %s", candidate.path)
                continue
            seen.add(candidate.key)
            existing = previous.pop(candidate.key, None)
            if existing is None:
                current.append(candidate)
                added.append(candidate)
            elif getattr(existing, "path", None) != getattr(candidate, "path", None):
                # The same physical camera may return under a different video
                # node after reconnect. Keep the newly opened valid descriptor.
                current.append(candidate)
                added.append(candidate)
                retired.append(existing)
            else:
                try:
                    candidate.close()
                except OSError:
                    LOGGER.exception("Could not close duplicate camera %s", candidate.path)
                current.append(existing)

        removed = [*previous.values(), *retired]
        self._devices = current
        return DeviceChange(tuple(current), tuple(added), tuple(removed))

    def close(self) -> None:
        devices, self._devices = self._devices, []
        for device in devices:
            try:
                device.close()
            except OSError:
                LOGGER.exception("Could not close camera %s", device.path)
