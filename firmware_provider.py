"""Firmware capability boundary.

Firmware actions remain unavailable until a trusted provider supports the exact
camera. This deliberately contains no raw or reverse-engineered flashing path.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FirmwareState:
    available: bool
    version: str
    status: str


class FirmwareProvider:
    def state_for(self, _camera) -> FirmwareState:
        return FirmwareState(
            available=False,
            version="Unavailable",
            status="No trusted firmware provider supports this camera.",
        )
