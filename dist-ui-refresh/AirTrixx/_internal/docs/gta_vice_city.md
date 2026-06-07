# GTA Vice City Control

AirTrixx includes a built-in **GTA Vice City** mapping profile for the running game window. It targets these process names:

- `Mss32.exe`
- `gta-vc.exe`
- `ViceCity.exe`

The profile sends keyboard movement controls and mouse-wheel weapon swaps. AirTrixx never sends mouse movement or clicks. Vice City itself may center the Windows cursor while the game is active, which is normal for this game.

## Activate

1. Start GTA: Vice City and load into the game.
2. Start AirTrixx and connect the camera dock, wristband, and USB antenna.
3. Open **Mappings** and click **GTA Vice City Mode**.
4. AirTrixx brings the game window forward once. Gesture controls run only while GTA: Vice City remains the active window.

## Default controls

| AirTrixx input | GTA control | Result |
|---|---|---|
| Move right hand forward | Hold `W` + `Space` | Run forward |
| Move right hand backward | Hold `S` | Walk reverse |
| Move left open palm physically right | Hold `D` | Turn right |
| Move left open palm physically left | Hold `A` | Turn left |
| Raise right hand | Tap `Ctrl` | Jump |
| Rotate wristband clockwise | Scroll one step | Swap to next weapon |
| Rotate wristband counterclockwise | Scroll one step opposite | Swap to previous weapon |

Right-hand forward/back uses the camera dock ToF distance relative to the first neutral hand position. Left-palm turning and right-hand jump use positions relative to their neutral camera positions. Return hands to a comfortable neutral position before moving them into a control gesture. Camera gestures use dead zones and short debounce periods to reject tracking noise. Wrist weapon swaps are one-shot detections, so one rotation swaps one weapon step.

## Train personalized gestures

Open **Gesture Recorder** and train these GTA actions:

1. Select a GTA action and click **Select**.
2. Record at least five repetitions. Begin each repetition in a comfortable neutral pose, perform the movement, hold it briefly, then return to neutral.
3. Repeat for `run_forward`, `walk_reverse`, `turn_right`, `turn_left`, `jump`, `swap_weapon_next`, and `swap_weapon_previous`.
4. Click **Train / Reload GTA Controls**. Training also runs automatically after each GTA recording finishes.

AirTrixx learns your camera movement distances, movement directions, wristband mounting orientation, and wrist rotation sensitivity. A gesture is applied after at least three valid samples are available. Re-recording a gesture and training again replaces its personalized calibration.

## Safety

- Disarm mappings before typing in another application.
- Held movement keys release when the gesture ends, the profile changes, or mappings are disarmed.
- If the game process is unavailable or is not the active window, no game input is sent.
- Gestures never steal focus from another application after GTA Vice City Mode is activated.
