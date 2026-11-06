# PyInstaller spec for the macOS app. Build with packaging/build_mac.sh.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
VERSION = "0.8.1"

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "ui"), "ui")],
    # imported inside functions / by name
    hiddenimports=["features.parcels", "features.sysmon", "features.poke", "features.usb", "usbscan", "driverinfo", "airprint", "menubar", "menus", "power",
                   "mail_scanner", "tracker", "skinmaker", "skinmaker.pipeline", "skinmaker.providers",
                   "keyring.backends.macOS", "webview.platforms.cocoa"],
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
)
# raw image generations of custom skins don't belong in the app
a.datas = [d for d in a.datas if "/_work/" not in d[0]]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Parcel Widget", console=False,
          argv_emulation=False, target_arch=None)
coll = COLLECT(exe, a.binaries, a.datas, name="Parcel Widget")
app = BUNDLE(
    coll,
    name="Parcel Widget.app",
    icon=os.path.join(SPECPATH, "icon.icns"),
    bundle_identifier="com.parcelwidget.app",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Parcel Widget",
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,                 # menu bar app: no Dock icon
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
)
