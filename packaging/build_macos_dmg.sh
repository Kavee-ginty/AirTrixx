#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
VENV_DIR="${ROOT_DIR}/.venv-build-macos"
DIST_DIR="${ROOT_DIR}/dist"
OUT_DIR="${ROOT_DIR}/.dist"
DMG_ROOT="${OUT_DIR}/dmgroot"
DMG_PATH="${OUT_DIR}/AirTrixx-mac-arm64.dmg"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS DMG builds must run on macOS."
  exit 2
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "This script builds the Apple Silicon DMG. Run it on an arm64 Mac."
  exit 2
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in python3.11 python3.12 python3.13; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      PYTHON_BIN="${candidate}"
      break
    fi
  done
fi

if [[ -z "${PYTHON_BIN}" ]] || ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python 3.11, 3.12, or 3.13 is required. Set PYTHON_BIN=/path/to/python if needed."
  exit 2
fi

cd "${ROOT_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r python_app/requirements.txt -r packaging/requirements-build.txt
python packaging/make_icons.py
python packaging/download_models.py
python -m PyInstaller --noconfirm --clean packaging/AirTrixx.spec

APP_PATH="${DIST_DIR}/AirTrixx.app"
if [[ ! -d "${APP_PATH}" ]]; then
  echo "PyInstaller did not produce ${APP_PATH}."
  exit 1
fi

rm -rf "${DMG_ROOT}" "${DMG_PATH}"
mkdir -p "${DMG_ROOT}" "${OUT_DIR}"
cp -R "${APP_PATH}" "${DMG_ROOT}/AirTrixx.app"
ln -s /Applications "${DMG_ROOT}/Applications"
hdiutil create -volname "AirTrixx" -srcfolder "${DMG_ROOT}" -ov -format UDZO "${DMG_PATH}"

echo "Built ${APP_PATH}"
echo "Built ${DMG_PATH}"
