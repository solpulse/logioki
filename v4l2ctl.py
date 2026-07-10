"""Minimal v4l2 control backend using raw ioctls — no external dependencies."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import glob
import os
import re
from contextlib import suppress
from dataclasses import dataclass

VIDIOC_QUERYCAP = 0x80685600
VIDIOC_QUERYCTRL = 0xC0445624
VIDIOC_QUERYMENU = 0xC02C5625
VIDIOC_G_CTRL = 0xC008561B
VIDIOC_S_CTRL = 0xC008561C

V4L2_CTRL_FLAG_NEXT_CTRL = 0x80000000
V4L2_CTRL_FLAG_NEXT_COMPOUND = 0x40000000
V4L2_CTRL_FLAG_DISABLED = 0x0001
V4L2_CTRL_FLAG_READ_ONLY = 0x0004
V4L2_CTRL_FLAG_INACTIVE = 0x0010

V4L2_CAP_VIDEO_CAPTURE = 0x00000001
V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
V4L2_CAP_DEVICE_CAPS = 0x80000000

TYPE_INT = 1
TYPE_BOOL = 2
TYPE_MENU = 3
TYPE_CLASS = 6
TYPE_INTEGER_MENU = 9

MAX_CONTROLS = 1024
MAX_MENU_ITEMS = 1024


class _queryctrl(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("name", ctypes.c_char * 32),
        ("minimum", ctypes.c_int32),
        ("maximum", ctypes.c_int32),
        ("step", ctypes.c_int32),
        ("default_value", ctypes.c_int32),
        ("flags", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 2),
    ]


class _control(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("value", ctypes.c_int32)]


class _querymenu(ctypes.Structure):
    class _u(ctypes.Union):
        _fields_ = [("name", ctypes.c_char * 32), ("value", ctypes.c_int64)]

    _fields_ = [
        ("id", ctypes.c_uint32),
        ("index", ctypes.c_uint32),
        ("u", _u),
        ("reserved", ctypes.c_uint32),
    ]
    _anonymous_ = ("u",)


class _capability(ctypes.Structure):
    _fields_ = [
        ("driver", ctypes.c_char * 16),
        ("card", ctypes.c_char * 32),
        ("bus_info", ctypes.c_char * 32),
        ("version", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint32),
        ("device_caps", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 3),
    ]


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


@dataclass(slots=True)
class Control:
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

    @classmethod
    def from_query(cls, query, menu_items: list[tuple[int, str]]) -> Control:
        # Integer-menu controls use the same UI and set/get semantics as menus.
        control_type = TYPE_MENU if query.type == TYPE_INTEGER_MENU else query.type
        return cls(
            id=query.id,
            name=_decode(query.name),
            type=control_type,
            minimum=query.minimum,
            maximum=query.maximum,
            step=query.step or 1,
            default=query.default_value,
            inactive=bool(query.flags & V4L2_CTRL_FLAG_INACTIVE),
            read_only=bool(query.flags & V4L2_CTRL_FLAG_READ_ONLY),
            menu_items=menu_items,
        )


class Camera:
    """One capture device: control enumeration, get/set, identity key."""

    def __init__(self, path: str):
        self.path = path
        self.fd: int | None = None
        self._identity: tuple[str, str, str] | None = None
        self.controls: list[Control] = []
        self.groups: dict[str, list[Control]] = {}
        try:
            self.fd = os.open(path, os.O_RDWR)
            cap = _capability()
            fcntl.ioctl(self.fd, VIDIOC_QUERYCAP, cap)
            self.card = _decode(cap.card)
            self.bus_info = _decode(cap.bus_info)
            capability_flags = (
                cap.device_caps if cap.capabilities & V4L2_CAP_DEVICE_CAPS else cap.capabilities
            )
            self.is_capture = bool(
                capability_flags & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE)
            )
            if self.is_capture:
                self._enumerate()
        except Exception:
            with suppress(OSError):
                self.close()
            raise

    def close(self) -> None:
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()

    def _fileno(self) -> int:
        if self.fd is None:
            raise OSError(errno.EBADF, "camera is closed")
        return self.fd

    @property
    def key(self) -> str:
        """Stable per-device identity that survives /dev/videoN renumbering."""
        serial, vendor, product = self._usb_identity()
        if serial:
            return f"usb:{vendor}:{product}:{serial}"
        # UVC bus_info includes the physical USB path. It distinguishes two
        # identical cameras even when their firmware exposes no serial number.
        return f"bus:{self.card}:{self.bus_info}"

    @property
    def identity_label(self) -> str:
        serial, _vendor, _product = self._usb_identity()
        return serial or self.bus_info

    def _usb_identity(self) -> tuple[str, str, str]:
        """Find USB IDs and serial by walking this video node's sysfs parents."""
        if self._identity is not None:
            return self._identity
        node = os.path.basename(self.path)
        current = os.path.realpath(f"/sys/class/video4linux/{node}/device")
        while current and current != "/":
            vendor_path = os.path.join(current, "idVendor")
            product_path = os.path.join(current, "idProduct")
            if os.path.exists(vendor_path) and os.path.exists(product_path):
                try:
                    with open(vendor_path, encoding="ascii", errors="replace") as f:
                        vendor = f.read().strip()
                    with open(product_path, encoding="ascii", errors="replace") as f:
                        product = f.read().strip()
                    try:
                        with open(
                            os.path.join(current, "serial"),
                            encoding="utf-8",
                            errors="replace",
                        ) as f:
                            serial = f.read().strip()
                    except OSError:
                        serial = ""
                    self._identity = (serial, vendor, product)
                    return self._identity
                except OSError:
                    break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        self._identity = ("", "unknown", "unknown")
        return self._identity

    def _enumerate(self):
        qc = _queryctrl()
        qc.id = V4L2_CTRL_FLAG_NEXT_CTRL | V4L2_CTRL_FLAG_NEXT_COMPOUND
        group = "Controls"
        seen_ids: set[int] = set()
        while len(seen_ids) < MAX_CONTROLS:
            try:
                fcntl.ioctl(self._fileno(), VIDIOC_QUERYCTRL, qc)
            except OSError as exc:
                if exc.errno == errno.EINVAL:
                    break
                raise
            if qc.id in seen_ids:
                break
            seen_ids.add(qc.id)
            if qc.type == TYPE_CLASS:
                group = _decode(qc.name)
            elif not qc.flags & V4L2_CTRL_FLAG_DISABLED and qc.type in (
                TYPE_INT,
                TYPE_BOOL,
                TYPE_MENU,
                TYPE_INTEGER_MENU,
            ):
                menu_items = []
                if qc.type in (TYPE_MENU, TYPE_INTEGER_MENU):
                    menu_end = min(qc.maximum, qc.minimum + MAX_MENU_ITEMS - 1)
                    for i in range(qc.minimum, menu_end + 1):
                        qm = _querymenu()
                        qm.id = qc.id
                        qm.index = i
                        try:
                            fcntl.ioctl(self._fileno(), VIDIOC_QUERYMENU, qm)
                            label = (
                                str(qm.value) if qc.type == TYPE_INTEGER_MENU else _decode(qm.name)
                            )
                            menu_items.append((i, label))
                        except OSError as exc:
                            if exc.errno != errno.EINVAL:
                                raise
                ctrl = Control.from_query(qc, menu_items)
                self.controls.append(ctrl)
                self.groups.setdefault(group, []).append(ctrl)
            qc.id |= V4L2_CTRL_FLAG_NEXT_CTRL | V4L2_CTRL_FLAG_NEXT_COMPOUND

    def get(self, ctrl_id: int) -> int:
        c = _control()
        c.id = ctrl_id
        fcntl.ioctl(self._fileno(), VIDIOC_G_CTRL, c)
        return c.value

    def set(self, ctrl_id: int, value: int) -> None:
        c = _control()
        c.id = ctrl_id
        c.value = value
        fcntl.ioctl(self._fileno(), VIDIOC_S_CTRL, c)

    def refresh_flags(self) -> None:
        """Re-query INACTIVE flags (e.g. WB temperature gated by auto WB)."""
        qc = _queryctrl()
        for ctrl in self.controls:
            qc.id = ctrl.id
            try:
                fcntl.ioctl(self._fileno(), VIDIOC_QUERYCTRL, qc)
                ctrl.inactive = bool(qc.flags & V4L2_CTRL_FLAG_INACTIVE)
                ctrl.read_only = bool(qc.flags & V4L2_CTRL_FLAG_READ_ONLY)
            except OSError:
                pass


def list_cameras() -> list[Camera]:
    """All capture devices that expose at least one control."""
    cams = []

    def device_number(path):
        match = re.fullmatch(r"/dev/video(\d+)", path)
        return int(match.group(1)) if match else float("inf")

    paths = (path for path in glob.glob("/dev/video*") if re.fullmatch(r"/dev/video\d+", path))
    for path in sorted(paths, key=device_number):
        try:
            cam = Camera(path)
        except OSError:
            continue
        if cam.is_capture and cam.controls:
            cams.append(cam)
        else:
            cam.close()
    return cams
