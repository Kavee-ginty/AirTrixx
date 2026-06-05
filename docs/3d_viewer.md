# 3D Viewer Control

AirTrixx can control dedicated 3D viewers through the built-in **`3dviewer.net`** mapping profile. The app translates right-hand MediaPipe gestures and wristband motion into OS mouse events that match standard browser viewer navigation.

CAD and modeling tools (Blender, Fusion 360, FreeCAD) mix editing with viewing and are poor first targets. Use simple viewers with consistent mouse navigation instead.

## Recommended viewers

| Viewer | Notes | Mouse pattern |
|--------|-------|---------------|
| [3dviewer.net](https://3dviewer.net) | First supported target; open source, 40+ formats | Left-drag orbit, right-drag pan, wheel zoom, click select |
| Sketchfab embed | Popular sharing platform | Same mouse model |
| Windows 3D Viewer | Native Windows app for `.glb` / `.stl` | Same mouse model |
| Babylon.js Sandbox | Developer-friendly web viewer | Same mouse model |
| Google `<model-viewer>` | Simple embed | Rotate + zoom only (limited pan) |

Future profiles can clone the `3dviewer.net` rules for any viewer that uses the same mouse navigation.

## Quick start

1. Connect the USB Antenna and start AirTrixx.
2. Open **Mappings** and click **3D Viewer Mode**.
   - Switches to the `3dviewer.net` profile
   - Arms mappings
   - Opens [https://3dviewer.net](https://3dviewer.net) in your default browser
3. Load a model in the browser (drag-and-drop a file, or use a URL hash link).
4. Click the browser canvas once so it has keyboard/mouse focus.
5. Keep the AirTrixx camera preview visible so hand tracking stays active.

Sample model URL:

```text
https://3dviewer.net/#model=https://raw.githubusercontent.com/kovacsv/Online3DViewer/dev/test/testfiles/gltf/DamagedHelmet/glTF-Binary/DamagedHelmet.glb
```

## Gesture cheat sheet

| Action | Gesture / signal | Viewer behavior |
|--------|------------------|-----------------|
| Orbit | Left hand closed fist + move right hand | Left-drag orbit |
| Pan | Right hand closed fist | Right-drag pan |
| Point / move cursor | Right hand index finger up | Move cursor over canvas |
| Select | Hold index finger up ~350 ms | Left click |
| Zoom in | Index finger up + hand ~25 mm closer (Cam Dock depth), or wrist pitch up | Scroll up |
| Zoom out | Index finger up + hand ~25 mm farther, or wrist pitch down | Scroll down |

Recognition labels (`3dviewer zoom in`, `3dviewer select`, etc.) appear briefly on the camera preview overlay when those actions fire.

## Hardware requirements

| Component | Required for |
|-----------|--------------|
| USB Antenna connected | Mappings run only while serial is connected |
| Webcam | MediaPipe right-hand tracking |
| Wristband | Wrist pitch zoom |
| Cam Dock ToF | Hand depth zoom while pointing |

Hand-only orbit and pan work with camera tracking alone. Zoom needs wristband pitch and/or Cam Dock depth depending on which gesture you use.

## Manual live-test checklist

Use this checklist after enabling **3D Viewer Mode**:

- [ ] Browser opens to 3dviewer.net and a model loads
- [ ] Browser canvas has focus (click it once)
- [ ] Mappings status shows **armed**
- [ ] Left closed fist + right hand moving: model orbits
- [ ] Right closed fist: model pans while hand moves
- [ ] Right index finger: cursor follows hand; click selects after brief hold
- [ ] Wrist pitch up/down: zoom in/out
- [ ] Pointing + moving hand closer/farther: zoom in/out (Cam Dock required)
- [ ] Switching gestures releases the previous mouse button (no stuck drag)

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Nothing happens in the browser | Confirm mappings are **armed**, Antenna is connected, and the browser canvas is focused |
| Cursor jumps or misses the canvas | Use a maximized/fullscreen browser window; hand position maps to the full screen |
| Zoom does not work | Wear wristband for pitch zoom; ensure Cam Dock is online for depth zoom while pointing |
| Unwanted clicks when pointing | Index-finger click waits 350 ms before firing; hold the pose steadily |
| Mappings stop when typing | Expected: mappings suppress while a text field in AirTrixx has focus |
| Profile missing in dropdown | Click **Load** on the Mappings page; built-in profiles merge automatically on load |

## Technical notes

- Control path: fused sensor snapshot → `InputMapper` → `pynput` mouse/keyboard injection → browser viewer.
- Profile definition: `create_3dviewer_net_profile()` in `python_app/input_mapper.py`.
- Config file: `%APPDATA%\AirTrixx\input_mappings.json` on Windows.
