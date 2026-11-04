#!/bin/bash
# Build "Parcel Widget.app" and a .dmg to install it (macOS).
#   ./packaging/build_mac.sh      ->  dist/ParcelWidget-<version>-macOS-<arch>.dmg
# Needs the project venv (./install.command or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
"$PY" -m pip install -q "pyinstaller>=6"

"$PY" packaging/make_icon.py
rm -rf build "dist/Parcel Widget" "dist/Parcel Widget.app"
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/ParcelWidget.spec

VERSION=$(grep '^VERSION' packaging/ParcelWidget.spec | cut -d'"' -f2)
ARCH=$(uname -m)
DMG="dist/ParcelWidget-$VERSION-macOS-$ARCH.dmg"

# the disk image: the app + a shortcut to /Applications to drag it onto
STAGE=$(mktemp -d)
cp -R "dist/Parcel Widget.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "Parcel Widget" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"
echo "Built $DMG"
