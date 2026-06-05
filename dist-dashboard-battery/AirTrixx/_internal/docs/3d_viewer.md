# 3D Viewer Control

AirTrixx can control dedicated 3D viewers through the built-in **`3dviewer.net`** and **`Windows 3D Viewer`** mapping profiles. The app translates right-hand MediaPipe gestures and wristband motion into OS mouse events that match standard viewer navigation.

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
| Orbit right | Wristband hand rolls right | Proportional left-drag rotate right |
| Orbit left | Wristband hand rolls left | Proportional left-drag rotate left |
| Pan | Right hand closed fist | Middle-drag pan |
| Point / move cursor | Right hand index finger up | Move cursor over canvas |
| Zoom in | Both open hands move apart, index finger up + hand ~25 mm closer (Cam Dock depth), or wrist pitch up | Scroll up |
| Zoom out | Both open hands move closer, index finger up + hand ~25 mm farther, or wrist pitch down | Scroll down |

Wrist-roll orbit follows the measured wrist angle delta, so a larger wrist rotation produces a larger model rotation. A full wrist roll is mapped to roughly one full model turn in the browser viewer. Zoom uses larger wheel steps so each recognized gesture changes the model view more noticeably. Recognition labels (`zoom_in`, `zoom_out`, wrist rotate labels, etc.) appear briefly on the camera preview overlay when those actions fire.

When a 3D viewer gesture action is detected, AirTrixx first moves the cursor to the screen center and then executes the mapped drag or scroll action. Pointer-follow remains a direct cursor-follow rule so it can still place the cursor manually without triggering clicks.

## Hardware requirements

| Component | Required for |
|-----------|--------------|
| USB Antenna connected | Mappings run only while serial is connected |
| Webcam | MediaPipe hand tracking and two-hand zoom |
| Wristband | Wrist pitch zoom and wrist-roll orbit |
| Cam Dock ToF | Hand depth zoom while pointing |

Hand-only orbit and pan work with camera tracking alone. Zoom needs wristband pitch and/or Cam Dock depth depending on which gesture you use.

## Manual live-test checklist

Use this checklist after enabling either viewer mode:

- [ ] Target viewer opens and a model loads
- [ ] Viewer canvas has focus (click it once)
- [ ] Mappings status shows **armed**
- [ ] Left closed fist + right hand moving: model orbits
- [ ] Wristband hand roll right/left: model rotates right/left
- [ ] Right closed fist: model pans while hand moves, without browser right-click menus
- [ ] Right index finger: cursor follows hand without auto-clicking
- [ ] Both open hands apart/together: zoom in/out
- [ ] Viewer gestures start from the screen center before rotating, panning, or zooming
- [ ] Wrist pitch up/down: zoom in/out
- [ ] Pointing + moving hand closer/farther: zoom in/out (Cam Dock required)
- [ ] Switching gestures releases the previous mouse button (no stuck drag)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Nothing happens in the browser | Confirm mappings are **armed**, Antenna is connected, and the browser canvas is focused |
| Cursor jumps or misses the canvas | Use a maximized/fullscreen browser window; hand position maps to the full screen |
| Zoom does not work | Use both open palms for camera-only zoom; wear wristband for pitch zoom; ensure Cam Dock is online for depth zoom while pointing |
| Unwanted clicks while viewing | The viewer profile disables automatic select clicks and uses middle-drag for pan; reload mappings if an older profile is still active |
| Mappings stop when typing | Expected: mappings suppress while a text field in AirTrixx has focus |
| Profile missing in dropdown | Click **Load** on the Mappings page; built-in profiles merge automatically on load |

## Technical notes

- Control path: fused sensor snapshot -> `InputMapper` -> `pynput` mouse/keyboard injection -> browser viewer.
- Profile definitions: `create_3dviewer_net_profile()` and `create_windows_3d_viewer_profile()` in `python_app/input_mapper.py`.
- Config file: `%APPDATA%\AirTrixx\input_mappings.json` on Windows.
