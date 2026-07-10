"""Minimal v4l2 control backend using raw ioctls — no external dependencies."""
import ctypes
import fcntl
import glob
import os

VIDIOC_QUERYCAP = 0x80685600
VIDIOC_QUERYCTRL = 0xc0445624
VIDIOC_QUERYMENU = 0xc02c5625
VIDIOC_G_CTRL = 0xc008561b
VIDIOC_S_CTRL = 0xc008561c

V4L2_CTRL_FLAG_NEXT_CTRL = 0x80000000
V4L2_CTRL_FLAG_NEXT_COMPOUND = 0x40000000
V4L2_CTRL_FLAG_DISABLED = 0x0001
V4L2_CTRL_FLAG_READ_ONLY = 0x0004
V4L2_CTRL_FLAG_INACTIVE = 0x0010

V4L2_CAP_VIDEO_CAPTURE = 0x00000001

TYPE_INT = 1
TYPE_BOOL = 2
TYPE_MENU = 3
TYPE_BUTTON = 4
TYPE_CLASS = 6


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


class Control:
    def __init__(self, qc, menu_items):
        self.id = qc.id
        self.name = qc.name.decode()
        self.type = qc.type
        self.minimum = qc.minimum
        self.maximum = qc.maximum
        self.step = qc.step or 1
        self.default = qc.default_value
        self.inactive = bool(qc.flags & V4L2_CTRL_FLAG_INACTIVE)
        self.read_only = bool(qc.flags & V4L2_CTRL_FLAG_READ_ONLY)
        self.menu_items = menu_items  # list of (index, label), valid entries only


class Camera:
    """One capture device: control enumeration, get/set, identity key."""

    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)
        cap = _capability()
        fcntl.ioctl(self.fd, VIDIOC_QUERYCAP, cap)
        self.card = cap.card.decode()
        self.bus_info = cap.bus_info.decode()
        self.is_capture = bool(cap.device_caps & V4L2_CAP_VIDEO_CAPTURE)
        self.controls = []
        self.groups = {}  # group name -> [Control]
        if self.is_capture:
            self._enumerate()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    @property
    def key(self):
        """Stable per-device identity that survives /dev/videoN renumbering."""
        serial, vendor, product = self._usb_identity()
        if serial:
            return f"usb:{vendor}:{product}:{serial}"
        # UVC bus_info includes the physical USB path. It distinguishes two
        # identical cameras even when their firmware exposes no serial number.
        return f"bus:{self.card}:{self.bus_info}"

    @property
    def identity_label(self):
        serial, _vendor, _product = self._usb_identity()
        return serial or self.bus_info

    def _usb_identity(self):
        """Find USB IDs and serial by walking this video node's sysfs parents."""
        node = os.path.basename(self.path)
        current = os.path.realpath(f"/sys/class/video4linux/{node}/device")
        while current and current != "/":
            vendor_path = os.path.join(current, "idVendor")
            product_path = os.path.join(current, "idProduct")
            if os.path.exists(vendor_path) and os.path.exists(product_path):
                try:
                    with open(vendor_path) as f:
                        vendor = f.read().strip()
                    with open(product_path) as f:
                        product = f.read().strip()
                    try:
                        with open(os.path.join(current, "serial")) as f:
                            serial = f.read().strip()
                    except OSError:
                        serial = ""
                    return serial, vendor, product
                except OSError:
                    break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return "", "unknown", "unknown"

    def _enumerate(self):
        qc = _queryctrl()
        qc.id = V4L2_CTRL_FLAG_NEXT_CTRL | V4L2_CTRL_FLAG_NEXT_COMPOUND
        group = "Controls"
        while True:
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERYCTRL, qc)
            except OSError:
                break
            if qc.type == TYPE_CLASS:
                group = qc.name.decode()
            elif not qc.flags & V4L2_CTRL_FLAG_DISABLED and qc.type in (
                TYPE_INT, TYPE_BOOL, TYPE_MENU,
            ):
                menu_items = []
                if qc.type == TYPE_MENU:
                    for i in range(qc.minimum, qc.maximum + 1):
                        qm = _querymenu()
                        qm.id = qc.id
                        qm.index = i
                        try:
                            fcntl.ioctl(self.fd, VIDIOC_QUERYMENU, qm)
                            menu_items.append((i, qm.name.decode()))
                        except OSError:
                            pass
                ctrl = Control(qc, menu_items)
                self.controls.append(ctrl)
                self.groups.setdefault(group, []).append(ctrl)
            qc.id |= V4L2_CTRL_FLAG_NEXT_CTRL | V4L2_CTRL_FLAG_NEXT_COMPOUND

    def get(self, ctrl_id):
        c = _control()
        c.id = ctrl_id
        fcntl.ioctl(self.fd, VIDIOC_G_CTRL, c)
        return c.value

    def set(self, ctrl_id, value):
        c = _control()
        c.id = ctrl_id
        c.value = value
        fcntl.ioctl(self.fd, VIDIOC_S_CTRL, c)

    def refresh_flags(self):
        """Re-query INACTIVE flags (e.g. WB temperature gated by auto WB)."""
        qc = _queryctrl()
        for ctrl in self.controls:
            qc.id = ctrl.id
            try:
                fcntl.ioctl(self.fd, VIDIOC_QUERYCTRL, qc)
                ctrl.inactive = bool(qc.flags & V4L2_CTRL_FLAG_INACTIVE)
                ctrl.read_only = bool(qc.flags & V4L2_CTRL_FLAG_READ_ONLY)
            except OSError:
                pass


def list_cameras():
    """All capture devices that expose at least one control."""
    cams = []
    for path in sorted(glob.glob("/dev/video*"), key=lambda p: int(p[10:] or 0)):
        try:
            cam = Camera(path)
        except OSError:
            continue
        if cam.is_capture and cam.controls:
            cams.append(cam)
        else:
            cam.close()
    return cams
