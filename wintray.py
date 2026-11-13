"""Windows: the icon in the notification area (system tray), and the same menu when you
right-click the character. The Windows side of what menubar.py does on macOS.

The icon is a little parcel box with cat ears; a red dot with a number on it when packages are
on their way (the tooltip says how many, and how many were delivered).
    left click      show / hide the character
    right click     the menu (menus.py), rebuilt every time it opens

pywebview's window on Windows is a Windows Forms window (through pythonnet), so the tray icon
and the menu are Windows Forms too: nothing extra to install. Everything that touches them runs
on the window's own thread (_ui); clicks are handled on a worker thread, because talking to the
web view from the menu's thread would deadlock.
"""
import os
import threading

import instance
import menus
from core import PROFILE, log

_NAME = "Parcel Widget"


def activate():
    """macOS needs this to bring an accessory app's windows forward; Windows doesn't"""


def _draw_icon(n):
    """the tray icon as a .ico file: a parcel box with cat ears, plus the count in a red dot"""
    from PIL import Image, ImageDraw, ImageFont
    S = 64
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box, edge, face = (214, 158, 96, 255), (92, 58, 28, 255), (60, 38, 20, 255)
    for ear in (((9, 30), (15, 6), (29, 26)), ((35, 26), (49, 6), (55, 30))):
        d.polygon(ear, fill=box, outline=edge)
        d.line(ear + (ear[0],), fill=edge, width=3, joint="curve")
    d.rounded_rectangle((6, 22, 58, 58), radius=8, fill=box, outline=edge, width=4)
    d.line((8, 34, 56, 34), fill=edge, width=3)                 # the lid
    for x in (23, 41):
        d.ellipse((x - 3, 40, x + 3, 46), fill=face)            # eyes
    d.arc((26, 44, 32, 52), 0, 180, fill=face, width=2)         # mouth
    d.arc((32, 44, 38, 52), 0, 180, fill=face, width=2)
    if n:
        d.ellipse((30, 0, 64, 34), fill=(229, 57, 53, 255), outline=(255, 255, 255, 255), width=2)
        text = str(n) if n < 10 else "9+"
        try:
            font = ImageFont.load_default(size=24 if n < 10 else 19)
        except TypeError:           # older Pillow: only the tiny built-in font
            font = ImageFont.load_default()
        d.text((47, 17), text, fill=(255, 255, 255, 255), font=font, anchor="mm")
    path = os.path.join(instance.BASE, "tray-%d-%d.ico" % (PROFILE, min(n, 10)))
    im.save(path, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64)])
    return path


class Tray:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self.menu = None          # the tray icon's menu
        self.pop = None           # the same menu, shown at the mouse (right-click on her)
        self._count = (0, 0)
        self._shown = None        # the count the icon shows now
        self._icons = []          # kept alive while the tray uses them

    # ---------- the window's thread ----------
    def _form(self):
        w = self.app.window
        f = getattr(w, "native", None)
        if f is None:
            from webview.platforms.winforms import BrowserView
            f = BrowserView.instances.get(w.uid)
        return f

    def _ui(self, fn):
        """run fn on the window's thread, soon (never blocks the caller)"""
        from System import Func, Type

        def run():
            try:
                fn()
            except Exception as ex:
                log("tray error %r" % ex)
        try:
            form = self._form()
            if form is None or form.IsDisposed:
                return
            form.BeginInvoke(Func[Type](run))
        except Exception as ex:
            log("tray error %r" % ex)

    # ---------- setup ----------
    def install(self):
        """call when the widget has started (any thread but the window's): waits for the
        character's window to exist, then puts the icon in the tray"""
        import time
        for _ in range(240):
            try:
                f = self._form()
                if f is not None and f.IsHandleCreated:
                    break
            except Exception:
                pass
            time.sleep(0.25)
        self._ui(self._create)

    def _create(self):
        import clr
        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Drawing")
        from System.Windows.Forms import ContextMenuStrip, NotifyIcon
        _no_taskbar_button(self._form())
        self.menu, self.pop = ContextMenuStrip(), ContextMenuStrip()
        self.menu.Opening += self._opening
        self.pop.Opening += self._opening
        self._fill(self.menu.Items, menus.spec(self.app))
        self.icon = NotifyIcon()
        self.icon.ContextMenuStrip = self.menu
        self.icon.MouseClick += self._clicked
        self._show_count()
        self.icon.Visible = True

    def remove(self):
        """take the icon out of the tray (otherwise it lingers until the mouse passes over it)"""
        try:
            if self.icon is not None:
                self.icon.Visible = False
                self.icon.Dispose()
                self.icon = None
        except Exception:
            pass

    # ---------- menu from data ----------
    def _opening(self, sender, e):
        try:
            self._fill(sender.Items, menus.spec(self.app))
            e.Cancel = False          # Windows Forms cancels a menu that was empty a moment ago
        except Exception as ex:
            log("tray menu error %r" % ex)

    def _fill(self, items, spec):
        from System.Windows.Forms import ToolStripMenuItem, ToolStripSeparator
        items.Clear()
        for it in spec:
            if it.get("sep"):
                items.Add(ToolStripSeparator())
                continue
            mi = ToolStripMenuItem(str(it["title"]).replace("&", "&&"))     # a single & would underline a letter
            key = it.get("key")
            mi.Checked = bool(it.get("checked"))
            mi.Enabled = bool(key or it.get("sub")) and it.get("enabled", True) and not it.get("info")
            if it.get("sub"):
                self._fill(mi.DropDownItems, it["sub"])
            elif key:
                mi.Click += self._handler(key)
            items.Add(mi)

    def _handler(self, key):
        def clicked(sender, e):
            self.dispatch(key)
        return clicked

    def _clicked(self, sender, e):
        try:
            from System.Windows.Forms import MouseButtons
            if e.Button == MouseButtons.Left:
                self.dispatch("app:show")
        except Exception as ex:
            log("tray error %r" % ex)

    def popup(self):
        """Show the menu at the mouse (right-click on the character). Thread-safe."""
        def show():
            from System.Windows.Forms import Cursor
            self._form().Activate()           # so a click elsewhere closes the menu
            self.pop.Show(Cursor.Position)
        if self.pop is not None:
            self._ui(show)

    def dispatch(self, key):
        threading.Thread(target=menus.handle, args=(self.app, key), daemon=True).start()

    # ---------- count on the icon ----------
    def _show_count(self):
        if self.icon is None:
            return
        n, d = self._count
        tag = " #%d" % PROFILE if PROFILE > 1 else ""       # which copy (instance.py)
        zh = self.app.cfg.get("lang") == "zh"
        tip = _NAME + tag
        if n or d:
            tip += (" · %d 个在路上" % n if zh else " · %d on the way" % n) if n else ""
            tip += (" · ✓ %d 个已送达" % d if zh else " · ✓ %d delivered" % d) if d else ""
        self.icon.Text = tip[:63]                           # Windows cuts tooltips off at 63 characters
        if self._shown != n:
            from System.Drawing import Icon
            ico = Icon(_draw_icon(n))
            self.icon.Icon = ico
            self._icons = (self._icons + [ico])[-2:]
            self._shown = n

    def set_count(self, n, delivered):
        """Thread-safe."""
        if (n, delivered) == self._count:
            return
        self._count = (n, delivered)
        if self.icon is not None:
            self._ui(self._show_count)


def _no_taskbar_button(form):
    """She lives in the tray, not on the taskbar (and not in Alt+Tab): make the character's
    window a "tool window". Done on the window handle directly: the Windows Forms way
    (ShowInTaskbar) rebuilds the window, which the web view inside doesn't survive well."""
    try:
        import ctypes
        u = ctypes.WinDLL("user32", use_last_error=True)
        get = getattr(u, "GetWindowLongPtrW", None) or u.GetWindowLongW
        put = getattr(u, "SetWindowLongPtrW", None) or u.SetWindowLongW
        get.restype = put.restype = ctypes.c_ssize_t
        get.argtypes = [ctypes.c_void_p, ctypes.c_int]
        put.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u.IsWindowVisible.argtypes = [ctypes.c_void_p]
        hwnd = form.Handle.ToInt64()
        shown = bool(u.IsWindowVisible(hwnd))
        ex = get(hwnd, -20)                                   # GWL_EXSTYLE
        if shown:
            u.ShowWindow(hwnd, 0)                             # the taskbar only notices the change on a hidden window
        put(hwnd, -20, (ex | 0x80) & ~0x40000)                # + WS_EX_TOOLWINDOW, - WS_EX_APPWINDOW
        if shown:
            u.ShowWindow(hwnd, 8)                             # SW_SHOWNA
    except Exception as ex:
        log("couldn't take the window off the taskbar: %r" % ex)
