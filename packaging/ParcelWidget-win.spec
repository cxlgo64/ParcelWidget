# PyInstaller spec for the Windows app. Build with packaging\build_win.bat.
#   dist\Parcel Widget\Parcel Widget.exe      the widget (no console window)
#   dist\Parcel Widget\ParcelWidgetHook.exe   the Claude Code hook (claude_hook.py) as a small console
#                                               program: Claude Code talks to hooks through pipes,
#                                               and there may be no Python on the PC to run the script
import os
import re

from PyInstaller.utils.hooks import collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
# one version number for both systems: the one in ParcelWidget.spec
VERSION = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(SPECPATH, "ParcelWidget.spec"), encoding="utf-8").read(),
                    re.M).group(1)
ICON = os.path.join(SPECPATH, "icon.ico")       # made by packaging/make_icon.py

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "ui"), "ui"), (os.path.join(ROOT, "claude_hook.py"), ".")]
    + collect_data_files("tzdata"),             # time zones (Windows has no database of its own)
    # imported inside functions / by name
    hiddenimports=["features.parcels", "features.mail", "mailread", "features.claude", "features.chat", "features.codex",
                   "features.github", "features.sysmon", "features.poke", "features.usb", "usbscan_win", "driverinfo",
                   "winprint", "instance", "vault", "plat", "wintray", "menus", "power", "claude_hook",
                   "mail_scanner", "tracker", "skinmaker", "skinmaker.pipeline", "skinmaker.providers",
                   "keyring.backends.Windows", "webview.platforms.winforms", "webview.platforms.edgechromium",
                   "tzdata", "tkinter", "tkinter.ttk"],
    excludes=["pytest", "IPython"],
    noarchive=False,
)
# raw image generations of custom skins don't belong in the app
a.datas = [d for d in a.datas if "/_work/" not in d[0].replace("\\", "/")]

h = Analysis([os.path.join(ROOT, "claude_hook.py")], pathex=[ROOT],
             excludes=["tkinter", "pytest", "IPython", "webview", "PIL", "numpy", "playwright", "psutil", "keyring"])

exe = EXE(PYZ(a.pure), a.scripts, [], exclude_binaries=True, name="Parcel Widget", console=False,
          icon=ICON if os.path.exists(ICON) else None)
hook = EXE(PYZ(h.pure), h.scripts, [], exclude_binaries=True, name="ParcelWidgetHook", console=True,
           icon=ICON if os.path.exists(ICON) else None)
coll = COLLECT(exe, hook, a.binaries, a.datas, h.binaries, h.datas, name="Parcel Widget")
