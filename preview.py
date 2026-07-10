"""GTK camera preview backed by a small, bounded GStreamer pipeline."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import Gdk, GLib, Gst, GstVideo, Gtk  # noqa: E402

PREVIEW_WIDTH, PREVIEW_HEIGHT = 1280, 720
Gst.init(None)
PIPELINE_DESCRIPTION = (
    "v4l2src name=source ! decodebin ! videoconvert ! videoscale add-borders=true ! "
    f"video/x-raw,format=RGB,width={PREVIEW_WIDTH},height={PREVIEW_HEIGHT},"
    "pixel-aspect-ratio=1/1 ! "
    "appsink name=sink max-buffers=1 drop=true emit-signals=true sync=false"
)


class Preview(Gtk.Picture):
    """Live preview that keeps at most one frame queued for GTK."""

    def __init__(self, on_error: Callable[[str], None] | None = None):
        super().__init__()
        self.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.add_css_class("card")
        self.pipeline = None
        self._bus = None
        self._bus_handler = 0
        self._idle_id = 0
        self._pending = False
        self._on_error_callback = on_error

    def start(self, device_path: str) -> None:
        self.stop()
        try:
            pipeline = Gst.parse_launch(PIPELINE_DESCRIPTION)
            pipeline.get_by_name("source").set_property("device", device_path)
            pipeline.get_by_name("sink").connect("new-sample", self._on_sample)
        except (GLib.Error, AttributeError) as exc:
            self._report_error(f"Could not create preview: {exc}")
            return

        self.pipeline = pipeline
        self._bus = pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus_handler = self._bus.connect("message", self._on_bus_message)
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._report_error("The camera preview could not be started")
            self.stop()

    def stop(self) -> None:
        if self._idle_id:
            GLib.source_remove(self._idle_id)
            self._idle_id = 0
        self._pending = False
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if self._bus is not None:
            if self._bus_handler:
                self._bus.disconnect(self._bus_handler)
                self._bus_handler = 0
            self._bus.remove_signal_watch()
            self._bus = None
        self.set_paintable(None)

    def _on_bus_message(self, _bus, message) -> None:
        if message.type == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            self._report_error(f"Preview stopped: {error.message}")
            if self.pipeline is not None:
                self.pipeline.set_state(Gst.State.NULL)
        elif message.type == Gst.MessageType.EOS:
            self._report_error("Preview stream ended")

    def _on_sample(self, sink):
        sample = sink.emit("pull-sample")
        if sample is None or self._pending:
            return Gst.FlowReturn.OK
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        try:
            info = GstVideo.VideoInfo.new_from_caps(caps)
            width, height = info.width, info.height
            stride = info.stride[0]
        except (GLib.Error, TypeError, ValueError):
            return Gst.FlowReturn.ERROR
        mapped, map_info = buffer.map(Gst.MapFlags.READ)
        if not mapped:
            return Gst.FlowReturn.ERROR
        try:
            data = bytes(map_info.data)
        finally:
            buffer.unmap(map_info)
        self._pending = True
        self._idle_id = GLib.idle_add(self._show_frame, data, width, height, stride)
        return Gst.FlowReturn.OK

    def _show_frame(self, data: bytes, width: int, height: int, stride: int):
        self._idle_id = 0
        if self.pipeline is not None:
            texture = Gdk.MemoryTexture.new(
                width,
                height,
                Gdk.MemoryFormat.R8G8B8,
                GLib.Bytes.new(data),
                stride,
            )
            self.set_paintable(texture)
        self._pending = False
        return GLib.SOURCE_REMOVE

    def _report_error(self, message: str) -> None:
        if self._on_error_callback is not None:
            GLib.idle_add(self._on_error_callback, message)
