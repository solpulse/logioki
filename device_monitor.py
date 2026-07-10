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
        self._devices = list(initial)

    @property
    def devices(self) -> tuple[CameraDevice, ...]:
        return tuple(self._devices)

    def refresh(self) -> DeviceChange:
        discovered = list(self._discover())
        previous = {device.key: device for device in self._devices}
        current: list[CameraDevice] = []
        added: list[CameraDevice] = []

        for candidate in discovered:
            existing = previous.pop(candidate.key, None)
            if existing is None:
                current.append(candidate)
                added.append(candidate)
            else:
                try:
                    candidate.close()
                except OSError:
                    LOGGER.exception("Could not close duplicate camera %s", candidate.path)
                current.append(existing)

        removed = list(previous.values())
        self._devices = current
        return DeviceChange(tuple(current), tuple(added), tuple(removed))

    def close(self) -> None:
        devices, self._devices = self._devices, []
        for device in devices:
            device.close()
