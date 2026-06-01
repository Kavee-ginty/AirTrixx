# AirTrixx Packaging

AirTrixx uses PyInstaller `onedir` builds so OpenCV, MediaPipe, Tkinter, pyserial, Pillow, and pynput native dependencies remain debuggable inside the bundle.

## macOS Apple Silicon DMG

Run on an arm64 Mac with Python 3.11, 3.12, or 3.13 installed:

```bash
./packaging/build_macos_dmg.sh
```

Output:

- `dist/AirTrixx.app`
- `.dist/AirTrixx-mac-arm64.dmg`

The first release is unsigned except for PyInstaller/macOS ad-hoc signing. Users may need to approve the app in macOS Security settings and grant Camera plus Accessibility/Input Monitoring permissions.

## Windows x64 Installer

Run on Windows x64 with Python 3.11, 3.12, or 3.13 installed:

```powershell
.\packaging\build_windows_installer.ps1
```

If Inno Setup is installed, the script creates `.dist\AirTrixxSetup-windows-x64.exe`. If `ISCC.exe` is unavailable, it creates `.dist\AirTrixx-windows-x64.zip` as a portable fallback.

## Notes

PyInstaller is OS-specific, so build the Windows installer on Windows and the macOS DMG on macOS. The app stores runtime data under the user's AirTrixx app-data folder, not inside the installed application bundle.
