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
| Rotate right | Rotate wristband forearm right | Direct smooth proportional left-drag rotate right |
| Rotate left | Rotate wristband forearm left | Direct smooth proportional left-drag rotate left |
| Pan | Right hand closed fist | Middle-drag pan |
| Point / move cursor | Right hand index finger up | Move cursor over canvas |
| Zoom in (`zoom_in` samples) | Both open palms move apart | Smooth single-step scroll up |
| Zoom out (`zoom_out` samples) | Both open palms move closer | Smooth single-step scroll down |

The camera orbit, pan, and pointer-follow rows apply to the `3dviewer.net` profile. The `Windows 3D Viewer` profile intentionally includes only wristband rotation and the two recorded zoom gestures, preventing accidental camera classifications from moving or clicking the normal cursor.

Forearm rotation directly controls the model using the wristband `gyro_y` angular velocity; it does not wait for a camera gesture or a one-shot rotation gesture. A live neutral baseline and dead zone suppress idle gyro drift, while angular velocity is continuously integrated into proportional orbit movement. In the Windows 3D Viewer profile, wristband orbit locates and activates the actual `3DViewer.exe` window and does nothing if that window is unavailable. It sends a synthetic touch drag directly to the Viewer, so wristband rotation never moves or clicks the normal system cursor. A short focus-settle phase ensures the orbit reaches the Viewer instead of the previously active app, and the action stops immediately if focus leaves the viewer. A short release grace period keeps one rotation active through brief neutral sensor gaps without repeatedly clicking. Individual steps are capped to prevent large rotation jumps. The recorded `rotate_left` and `rotate_right` samples tune direction and scaling. The recorded `zoom_in` and `zoom_out` samples are mapped from sustained changes in open-palm distance. A short rolling window ignores tracking wobble, and each zoom action sends one mouse-wheel notch, preventing the large zoom-level jumps caused by the old multi-notch action.

Camera-based 3D viewer gesture actions move the cursor to the screen center before executing their mapped drag or scroll action. Windows 3D Viewer wristband orbit is the exception: it uses viewer-targeted synthetic touch and leaves the normal cursor untouched. Pointer-follow remains available in the web viewer profile.

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
- [ ] Wristband forearm rotate right/left: model smoothly follows the recorded direction and amount
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

## Technical notes

- Control path: fused sensor snapshot -> `InputMapper` -> `pynput` mouse/keyboard injection -> browser viewer.
- Profile definitions: `create_3dviewer_net_profile()` and `create_windows_3d_viewer_profile()` in `python_app/input_mapper.py`.
- Config file: `%APPDATA%\AirTrixx\input_mappings.json` on Windows.
