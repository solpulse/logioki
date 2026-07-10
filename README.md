# Logioki

A native Linux control panel for Logitech (and any UVC) webcams — the missing
Logi Tune for Linux. GTK4/libadwaita, live preview, named image presets, and
settings that survive reboots.

UVC webcams forget all settings on power loss. Logioki saves every change to
`~/.config/logioki/settings.json` and re-applies it to the camera each time
the app opens. Automatic login restore is enabled by default; its systemd user
service waits up to 30 seconds for the camera, then restores settings without
opening the GUI. It can be disabled with **Apply at login**.

## Run

```sh
python3 logioki.py
```

Or launch **Logioki** from your desktop's app grid (installed via
`~/.local/share/applications/logioki.desktop`).

## Features

- Live 720p preview while you tune
- Automatically uses a GNOME/libadwaita interface on GNOME and a polished
  Plasma-oriented two-pane interface on KDE, with a large preview and tabbed
  settings inspector (`LOGIOKI_DESKTOP_STYLE=kde|gnome` can override it)
- All controls the camera exposes, discovered at runtime: brightness,
  contrast, saturation, sharpness, white balance (auto + temperature),
  exposure (auto/manual + time), gain, backlight compensation, focus
  (auto + manual), zoom, pan/tilt, power-line frequency
- Auto/manual dependencies handled (e.g. WB temperature greys out while
  auto white balance is on)
- Built-in Default, Streaming, and Video Calls presets
- Create, update, apply, and delete custom presets
- One-click reset to camera defaults
- Every restored value is read back from the camera; rejected settings are
  reported instead of silently treated as successful
- Instant apply, debounced save, settings keyed by USB serial number (or
  physical USB port when the device has no serial)
- Works with multiple cameras (device picker appears in the header bar)

## Files

- `logioki.py` — GTK4/libadwaita app; `--apply` flag restores settings
  headlessly (used by the login service)
- `v4l2ctl.py` — v4l2 control backend (raw ioctls, no dependencies)
- `store.py` — settings persistence and restore logic
- `tests/` — persistence, preset, identity, verification, and service tests

## Requirements

Python 3, GTK4 + libadwaita + GStreamer via PyGObject — all present on
stock Fedora Workstation. No pip packages, no root.

## Notes

- Capture **resolution** is not a camera setting: each recording app (OBS,
  browser, etc.) negotiates its own resolution with the camera. The MX Brio
  offers up to 4K@30 (MJPG) / 1080p@60 to any app that asks.
- Logitech vendor extras (HDR, FoV switching) live in UVC extension units
  and are not yet implemented here.

## Presets

Select a preset to apply it immediately. **Save Current** replaces the selected
Streaming, Video Calls, or custom preset with the camera's current values.
Default always remains the camera-reported factory defaults. **New…** creates a
custom preset from the current image, and the trash button deletes custom
presets. The last live camera state is restored at startup independently of
which named preset was last edited.
