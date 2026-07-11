# Logioki

A native Linux control panel for Logitech (and any UVC) webcams — the missing
Logi Tune for Linux. Qt Quick live preview, named image presets, and settings
that survive reboots. KDE and GNOME use the same adaptive interface.

UVC webcams forget all settings on power loss. Logioki saves every change to
`~/.config/logioki/settings.json` and re-applies it to the camera each time
the app opens. Optional login restore can be enabled with **Restore settings at login**;
its systemd user service waits up to 30 seconds for the camera, then restores
settings without opening the GUI.

## Run

```sh
python3 logioki.py
```

For a user installation from a source checkout:

```sh
python3 -m pip install --user '.[gui]'
logioki
```

Or launch **Logioki** from your desktop's app grid (the user installation places
`io.github.solpulse.Logioki.desktop` in your local applications directory).

## Features

- Capability-aware live preview that defaults to smooth 1080p60 when available,
  with every efficient camera mode—including MX Brio 4K30—selectable in the video HUD
- Plasma Cinematic workspace driven by the project design tokens: compact scene
  selector, fluid video canvas, detailed settings pane, and video-first responsive layout
- One responsive PySide6/Qt Quick interface with KDE-compact and
  GNOME-comfortable visual profiles (`LOGIOKI_DESKTOP_STYLE=kde|gnome` can override it)
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

- `logioki.py` — dependency-light application launcher
- `qml_app.py` — unified Qt Quick application bootstrap
- `application_view_model.py` — typed QML boundary and asynchronous orchestration
- `logioki_ui/qml/` — adaptive design tokens, components, and screens
- `DESIGN.md` — canonical Plasma Cinematic colors, typography, spacing, and component rules
- `models.py` — typed camera protocols and persistent settings models
- `device_monitor.py` — toolkit-neutral device discovery reconciliation
- `logioki_cli.py` — dependency-light installed command-line entry point
- `diagnostics.py` — redacted diagnostics and rotating local logs
- `startup_manager.py` — independent headless-restore and GUI login settings
- `service.py` — atomic systemd user-service management
- `v4l2ctl.py` — v4l2 control backend (raw ioctls, no dependencies)
- `store.py` — settings persistence and restore logic
- `tests/` — persistence, preset, identity, verification, and service tests
- `data/` — desktop launcher, AppStream metadata, and scalable application icon

QML talks only to the application view model. Hardware, persistence, startup, and
diagnostic services never depend on QML. The installed CLI keeps headless restore
independent of PySide6 and every other GUI dependency.

## Development

Run the same fast checks used by continuous integration:

```sh
python3 -m unittest discover -s tests -v
python3 -m ruff format --check .
python3 -m ruff check .
pyside6-qmllint -I logioki_ui logioki_ui/qml/*.qml
python3 -m bandit --recursive . --exclude ./.git,./tests \
  --severity-level medium --confidence-level medium
desktop-file-validate data/io.github.solpulse.Logioki.desktop
appstreamcli validate --no-net data/io.github.solpulse.Logioki.metainfo.xml
```

The complete CI job constructs both KDE and GNOME profiles from the same QML
application using `tests/ui_smoke.py`. Quality-tool versions are pinned in
`requirements-ci.txt`.

For the required MX Brio hardware acceptance run, select its primary capture
node explicitly. The write test re-applies each control's current value and
verifies the hardware readback, so it does not intentionally change the image:

```sh
LOGIOKI_TEST_CAMERA=/dev/video0 LOGIOKI_EXPECT_CAMERA='MX Brio' \
  python3 -m unittest tests.test_hardware -v
```

## Requirements

Python 3 and PySide6 6.7 or newer (`pip install 'logioki[gui]'`). PySide6 is not
imported by headless restore. The application does not need root access.

## Notes

- The **Preview mode** selector controls only Logioki's live preview. Recording
  apps such as OBS and browsers negotiate their own independent resolution.
  The MX Brio offers up to 4K@30 (MJPEG) and 1080p@60.
- Logitech vendor extras (HDR, FoV switching) live in UVC extension units
  and are not yet implemented here.

## Presets

Select a preset to apply it immediately. **Save Current** replaces the selected
Streaming, Video Calls, or custom preset with the camera's current values.
Default always remains the camera-reported factory defaults. **New…** creates a
custom preset from the current image, and the trash button deletes custom
presets. The last live camera state is restored at startup independently of
which named preset was last edited.

## License

Logioki is licensed under the Apache License 2.0. See `LICENSE`.
