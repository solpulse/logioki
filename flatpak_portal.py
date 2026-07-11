"""Qt D-Bus client for Flatpak background/autostart permission."""

from __future__ import annotations

import secrets

from PySide6.QtCore import SLOT, QEventLoop, QObject, QTimer, Slot
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage, QDBusVariant

PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
BACKGROUND_INTERFACE = "org.freedesktop.portal.Background"
REQUEST_INTERFACE = "org.freedesktop.portal.Request"


class _ResponseReceiver(QObject):
    def __init__(self, loop: QEventLoop):
        super().__init__()
        self.loop = loop
        self.response = None
        self.results = {}

    @Slot("uint", "QVariantMap")
    def receive(self, response, results):
        self.response = int(response)
        self.results = {
            key: value.variant() if isinstance(value, QDBusVariant) else value
            for key, value in results.items()
        }
        self.loop.quit()


def _expected_handle(connection, token: str) -> str:
    sender = connection.baseService().removeprefix(":").replace(".", "_")
    return f"{PORTAL_PATH}/request/{sender}/{token}"


def request_background(
    enabled: bool,
    commandline: list[str],
    timeout_ms: int = 120_000,
) -> tuple[bool, str | None]:
    """Request Flatpak autostart and wait for the portal's user decision."""
    connection = QDBusConnection.sessionBus()
    if not connection.isConnected():
        return False, "The desktop portal session bus is unavailable"

    token = f"logioki_{secrets.token_hex(8)}"
    handle = _expected_handle(connection, token)
    loop = QEventLoop()
    receiver = _ResponseReceiver(loop)
    slot = SLOT("receive(uint,QVariantMap)")
    connected = connection.connect(
        PORTAL_SERVICE,
        handle,
        REQUEST_INTERFACE,
        "Response",
        receiver,
        slot,
    )
    if not connected:
        return False, "Could not listen for the desktop portal response"

    options = {
        "handle_token": QDBusVariant(token),
        "reason": QDBusVariant("Restore camera settings when you sign in"),
        "autostart": QDBusVariant(bool(enabled)),
    }
    if enabled:
        options["commandline"] = QDBusVariant(commandline)
    message = QDBusMessage.createMethodCall(
        PORTAL_SERVICE,
        PORTAL_PATH,
        BACKGROUND_INTERFACE,
        "RequestBackground",
    )
    message.setArguments(["", options])
    reply = connection.call(message, QDBus.CallMode.Block, 25_000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        connection.disconnect(PORTAL_SERVICE, handle, REQUEST_INTERFACE, "Response", receiver, slot)
        return False, reply.errorMessage() or "The desktop portal request failed"

    returned_handle = reply.arguments()[0]
    returned_handle = (
        returned_handle.path() if hasattr(returned_handle, "path") else str(returned_handle)
    )
    if returned_handle != handle:
        connection.disconnect(PORTAL_SERVICE, handle, REQUEST_INTERFACE, "Response", receiver, slot)
        handle = returned_handle
        if not connection.connect(
            PORTAL_SERVICE,
            handle,
            REQUEST_INTERFACE,
            "Response",
            receiver,
            slot,
        ):
            return False, "Could not listen for the desktop portal response"

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()
    connection.disconnect(PORTAL_SERVICE, handle, REQUEST_INTERFACE, "Response", receiver, slot)
    if receiver.response is None:
        return False, "The desktop portal did not answer in time"
    if receiver.response != 0:
        return False, "The startup request was cancelled"
    if bool(receiver.results.get("autostart", enabled)) != enabled:
        return False, "The desktop did not grant the requested startup setting"
    return True, None
