# 3D Viewer Control

AirTrixx can control dedicated 3D viewers through the built-in **`3dviewer.net`** and **`Windows 3D Viewer`** mapping profiles. The app translates right-hand MediaPipe gestures and wristband motion into viewer navigation input.

CAD and modeling tools (Blender, Fusion 360, FreeCAD) mix editing with viewing and are poor first targets. Use simple viewers with consistent mouse navigation instead.

## Recommended viewers

| Viewer | Notes | Mouse pattern |
|--------|-------|---------------|
| [3dviewer.net](https://3dviewer.net) | First supported target; open source, 40+ formats | Left-drag orbit, middle-drag pan, wheel zoom |
| Sketchfab embed | Popular sharing platform | Similar mouse model |
| Windows 3D Viewer | Native Windows app for `.glb` / `.stl` | Similar mouse model |
| Babylon.js Sandbox | Developer-friendly web viewer | Similar mouse model |
| Google `<model-viewer>` | Simple embed | Rotate + zoom only (limited pan) |

Future profiles can clone these viewer rules for any tool that uses the same mouse navigation.

## Quick start

1. Connect the USB Antenna and start AirTrixx.
2. Open **Mappings** and click either **3dviewer.net Mode** or **Windows 3D Viewer Mode**.
   - Switches to the `3dviewer.net` profile
   - Or switches to the `Windows 3D Viewer` profile
   - Arms mappings
   - Opens [https://3dviewer.net](https://3dviewer.net) in your default browser, or launches Windows 3D Viewer if it is installed
3. Load a model in the viewer.
4. Click the viewer canvas once so it has keyboard/mouse focus.
5. Keep the AirTrixx camera preview visible so hand tracking stays active.

Sample model URL:

```text
https://3dviewer.net/#model=https://raw.githubusercontent.com/kovacsv/Online3DViewer/dev/test/testfiles/gltf/DamagedHelmet/glTF-Binary/DamagedHelmet.glb
```

## Gesture cheat sheet

| Action | Gesture / signal | Viewer behavior |
|--------|------------------|-----------------|
| Orbit | Left hand closed fist + move right hand | Left-drag orbit |
| Rotate right (`3dviewer.net`) | Rotate wristband forearm right | Direct smooth proportional left-drag rotate right |
| Rotate left (`3dviewer.net`) | Rotate wristband forearm left | Direct smooth proportional left-drag rotate left |
| Rotate right (`Windows 3D Viewer`) | Roll wristband right (roll angle increases) | Continuous touch-drag rotates model right |
| Rotate left (`Windows 3D Viewer`) | Roll wristband left (roll angle decreases) | Continuous touch-drag rotates model left |
| Pan | Right hand closed fist | Middle-drag pan |
| Point / move cursor | Right hand index finger up | Move cursor over canvas |
| Zoom in (`zoom_in` samples) | Both open palms move apart | Smooth single-step scroll up |
| Zoom out (`zoom_out` samples) | Both open palms move closer | Smooth single-step scroll down |

The camera orbit, pan, and pointer-follow rows apply to the `3dviewer.net` profile only.

### `3dviewer.net` wrist rotation

Forearm rotation uses wristband `gyro_y` angular velocity with a live neutral baseline and dead zone. It continuously integrates motion into proportional left-drag orbit in the browser.

### `Windows 3D Viewer` wrist rotation

The Windows profile uses **wrist roll angle velocity** (`wrist_roll`), not forearm gyro twist:

- Roll wristband **right** (roll angle increasing) → model rotates **right**
- Roll wristband **left** (roll angle decreasing) → model rotates **left**

Rotation stays active while roll speed stays above the threshold, with hysteresis so brief neutral gaps do not drop the drag. The rule locates `3DViewer.exe`, sends synthetic touch drag directly to the Viewer (never moving the system cursor), and stops if the Viewer loses focus. Per-frame movement is capped to prevent jumps.

Both viewer profiles include the recorded `zoom_in` and `zoom_out` open-palm distance gestures. Each zoom action sends one mouse-wheel notch.

Camera-based `3dviewer.net` gesture actions move the cursor to the screen center before drag or scroll. Windows 3D Viewer wrist rotation is the exception: viewer-targeted synthetic touch only.

## Hardware requirements

| Component | Required for |
|-----------|--------------|
| USB Antenna connected | Mappings run only while serial is connected |
| Webcam | MediaPipe hand tracking and recorded open-palm zoom |
| Wristband | Recorded forearm rotation |

Hand-only orbit, pan, and smooth zoom work with camera tracking alone.

## Manual live-test checklist

Use this checklist after enabling either viewer mode:

- [ ] Target viewer opens and a model loads
- [ ] Viewer canvas has focus (click it once)
- [ ] Mappings status shows **armed**
- [ ] Left closed fist + right hand moving: model orbits
- [ ] `3dviewer.net`: wristband forearm rotate right/left follows recorded direction
- [ ] `Windows 3D Viewer`: wrist roll right rotates model right; wrist roll left rotates model left continuously
- [ ] Right closed fist: model pans while hand moves, without browser right-click menus
- [ ] Right index finger: cursor follows hand without auto-clicking
- [ ] Both open palms moving apart: gradual zoom in with no large jump
- [ ] Both open palms moving closer: gradual zoom out with no large jump
- [ ] Viewer gestures start from the screen center before rotating, panning, or zooming
- [ ] Switching gestures releases the previous mouse button (no stuck drag)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Nothing happens in the browser | Confirm mappings are **armed**, Antenna is connected, and the browser canvas is focused |
| Cursor jumps or misses the canvas | Use a maximized/fullscreen browser window; hand position maps to the full screen |
| Zoom does not work | Keep both palms open and visible, then move them steadily apart or closer |
| Unwanted clicks while viewing | The viewer profile disables automatic select clicks and uses middle-drag for pan; reload mappings if an older profile is still active |
| Mappings stop when typing | Expected: mappings suppress while a text field in AirTrixx has focus |
| Profile missing in dropdown | Click **Load** on the Mappings page; built-in profiles merge automatically on load |
| Windows 3D Viewer rotation stops mid-gesture | Keep rolling steadily; rotation needs roll speed above ~6 deg/s. Reload mappings to pick up the roll-velocity profile |
| Windows rotation direction feels inverted | Report it; `WINDOWS_3D_VIEWER_ROLL_SIGN` in `input_mapper.py` can flip drag direction |

## Technical notes

- Control path: fused sensor snapshot -> `InputMapper` -> `pynput` mouse/keyboard injection -> browser viewer.
- Profile definitions: `create_3dviewer_net_profile()` and `create_windows_3d_viewer_profile()` in `python_app/input_mapper.py`.
- Config file: `%APPDATA%\AirTrixx\input_mappings.json` on Windows.
