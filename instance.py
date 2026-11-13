"""Which copy of the widget this is, decided before anything else starts (macOS and Windows).

Each copy is like an account: copy 1 keeps its data in the usual folder, copy 2, 3, ... in
Profiles/<n> next to it, each with its own settings, Gmail and parcels. A running copy holds a
lock on locks/<n>.lock (released by the system if it crashes).

At launch (choose()):
  - nothing open      -> start the copy used last, no questions
  - one already open  -> ask: go to the open one (it comes to the front), or open another one
                         (a copy that isn't open, or a new one)
  - started at login (launchd / the Startup folder's "--autostart") while one is open -> quietly do nothing
The open copy is brought forward with a system-wide notification (macOS) or a named event
(Windows): see listen().
"""
import json
import os
import sys
import time

from plat import IS_MAC, IS_WIN, lock_file, unlock_file

if IS_WIN:
    BASE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ParcelWidget")
else:
    BASE = os.path.expanduser("~/Library/Application Support/ParcelWidget")
STATE = os.path.join(BASE, "profiles.json")
SHOW = "com.parcelwidget.show"
LAUNCHD_LABEL = "com.parcelwidget.app"

T = {
    "en": {"title": "Parcel Widget is already open",
           "text": "Go to the one that's open, or open another one?\nEach one has its own settings and Gmail.",
           "go": "Go to it", "another": "Open another", "cancel": "Cancel",
           "which_go": "Which one:", "which_title": "Open which one?",
           "which_text": "Pick one that isn't open, or start a new one.",
           "open": "Open", "new": "New one", "name": lambda n: "No. %d" % n,
           "used": lambda t: "last used %s" % t},
    "zh": {"title": "快递小组件已经打开了",
           "text": "要切换到已经打开的那个，还是再开一个？\n每一个都有自己的设置和 Gmail。",
           "go": "切换过去", "another": "再开一个", "cancel": "取消",
           "which_go": "切换到：", "which_title": "打开哪一个？",
           "which_text": "选一个还没打开的，或者新建一个。",
           "open": "打开", "new": "新建一个", "name": lambda n: "%d 号" % n,
           "used": lambda t: "上次用 %s" % t},
}

_lock_file = None     # held for as long as this copy runs
_observer = None


def profile_dir(n):
    return BASE if n == 1 else os.path.join(BASE, "Profiles", str(n))


def profiles():
    """the copies that exist: 1 always, plus Profiles/<n>"""
    out = {1}
    try:
        out |= {int(x) for x in os.listdir(os.path.join(BASE, "Profiles")) if x.isdigit() and int(x) > 1}
    except OSError:
        pass
    return sorted(out)


def _lock_path(n):
    return os.path.join(BASE, "locks", "%d.lock" % n)


def is_running(n):
    try:
        with open(_lock_path(n), "ab") as f:
            if not lock_file(f):
                return True
            unlock_file(f)
        return False
    except OSError:
        return False


def _take(n):
    """hold copy n's lock; False if another process has it"""
    global _lock_file
    os.makedirs(os.path.dirname(_lock_path(n)), exist_ok=True)
    f = open(_lock_path(n), "ab")
    if not lock_file(f):
        f.close()
        return False
    _lock_file = f
    return True


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def _remember(n):
    s = _state()
    s["last"] = n
    s.setdefault("used", {})[str(n)] = time.time()
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
        os.replace(tmp, STATE)
    except OSError:
        pass


def _lang(n):
    try:
        with open(os.path.join(profile_dir(n), "config.json"), encoding="utf-8") as f:
            return "zh" if json.load(f).get("lang") == "zh" else "en"
    except Exception:
        return "en"


def _label(L, n, used):
    t = used.get(str(n))
    if not t:
        return L["name"](n)
    when = time.strftime("%m-%d %H:%M" if time.time() - t > 20 * 3600 else "%H:%M", time.localtime(t))
    return "%s  (%s)" % (L["name"](n), L["used"](when))


def _alert(title, text, buttons, choices=None, label=None):
    """a native dialog: (index of the button pressed, index picked in the list or None)"""
    if IS_WIN:
        return _alert_win(title, text, buttons, choices, label)
    import AppKit
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    app.activateIgnoringOtherApps_(True)
    a = AppKit.NSAlert.alloc().init()
    a.setMessageText_(title)
    a.setInformativeText_(text)
    for b in buttons:
        a.addButtonWithTitle_(b)
    a.buttons()[-1].setKeyEquivalent_("\x1b")     # Esc = the last button (Cancel)
    pop = None
    if choices:
        box = AppKit.NSView.alloc().initWithFrame_(((0, 0), (300, 26)))
        if label:
            lab = AppKit.NSTextField.labelWithString_(label)
            lab.setFrame_(((0, 3), (80, 20)))
            box.addSubview_(lab)
        pop = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(((84 if label else 0, 0), (216 if label else 300, 26)), False)
        for c in choices:
            pop.addItemWithTitle_(c)
        box.addSubview_(pop)
        a.setAccessoryView_(box)
    a.window().setLevel_(AppKit.NSFloatingWindowLevel)
    r = a.runModal()
    return r - AppKit.NSAlertFirstButtonReturn, (pop.indexOfSelectedItem() if pop else None)


def _alert_win(title, text, buttons, choices=None, label=None):
    """Windows: a small dialog (tkinter comes with Python); without it, a plain message box"""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return _msgbox_win(title, text, buttons, choices)
    res = {"btn": len(buttons) - 1, "pick": None}
    root = tk.Tk()
    root.title("Parcel Widget")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    box = ttk.Frame(root, padding=18)
    box.pack(fill="both", expand=True)
    ttk.Label(box, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w")
    ttk.Label(box, text=text, justify="left", wraplength=380).pack(anchor="w", pady=(6, 10))
    combo = None
    if choices:
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(0, 10))
        if label:
            ttk.Label(row, text=label).pack(side="left", padx=(0, 8))
        combo = ttk.Combobox(row, values=list(choices), state="readonly", width=34)
        combo.current(0)
        combo.pack(side="left", fill="x", expand=True)

    def press(i):
        res["btn"] = i
        res["pick"] = combo.current() if combo is not None else None
        root.destroy()
    row = ttk.Frame(box)
    row.pack(anchor="e")
    for i, b in enumerate(buttons):
        w = ttk.Button(row, text=b, command=lambda i=i: press(i))
        w.pack(side="left", padx=(8, 0))
        if i == 0:
            w.focus_set()
    root.bind("<Escape>", lambda e: press(len(buttons) - 1))     # Esc / closing = the last button (Cancel)
    root.bind("<Return>", lambda e: press(0))
    root.protocol("WM_DELETE_WINDOW", lambda: press(len(buttons) - 1))
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
    root.geometry("+%d+%d" % (x, y))
    root.mainloop()
    return res["btn"], res["pick"]


def _msgbox_win(title, text, buttons, choices=None):
    """Yes / No (/ Cancel) stand for the buttons, named in the text; the first choice is taken"""
    import ctypes
    names = ["Yes", "No", "Cancel"][:len(buttons)] if len(buttons) > 2 else ["OK", "Cancel"]
    body = "%s\n\n%s" % (text, "\n".join("%s = %s" % (k, b) for k, b in zip(names, buttons)))
    if choices:
        body += "\n\n(%s)" % choices[0]
    flags = (0x03 if len(buttons) > 2 else 0x01) | 0x40 | 0x40000      # buttons, info icon, topmost
    r = ctypes.windll.user32.MessageBoxW(None, body, title, flags)
    btn = {6: 0, 7: 1, 1: 0}.get(r, len(buttons) - 1)                  # IDYES, IDNO, IDOK; else the last
    return btn, (0 if choices else None)


def _event_name(n):
    return "Local\\ParcelWidget.show.%d" % int(n)


def bring_forward(n):
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenEventW.restype = wintypes.HANDLE
        k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        k32.SetEvent.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.OpenEventW(0x0002, False, _event_name(n))             # EVENT_MODIFY_STATE
        if h:
            k32.SetEvent(h)
            k32.CloseHandle(h)
        return
    import Foundation
    Foundation.NSDistributedNotificationCenter.defaultCenter() \
        .postNotificationName_object_userInfo_deliverImmediately_(SHOW, str(n), None, True)


def choose():
    """which copy to start (see the module doc); may end this process instead"""
    os.makedirs(BASE, exist_ok=True)
    forced = os.environ.get("PARCELWIDGET_PROFILE")
    if forced and forced.isdigit():
        n = int(forced)
        if not _take(n):
            bring_forward(n)
            sys.exit(0)
        return _started(n)
    if not (IS_MAC or IS_WIN):
        return _started(1) if _take(1) else sys.exit(0)

    s = _state()
    used = s.get("used", {})
    have = profiles()
    running = [n for n in have if is_running(n)]
    if not running:
        last = s.get("last") if s.get("last") in have else 1
        for n in [last] + [x for x in have if x != last]:
            if _take(n):
                return _started(n)
    if os.environ.get("XPC_SERVICE_NAME") == LAUNCHD_LABEL or "--autostart" in sys.argv:
        sys.exit(0)           # started at login, but one is open already

    running.sort(key=lambda n: -used.get(str(n), 0))
    L = T[_lang(running[0])]
    many = len(running) > 1
    btn, pick = _alert(L["title"], L["text"], [L["go"], L["another"], L["cancel"]],
                       [_label(L, n, used) for n in running] if many else None, L["which_go"])
    if btn == 0:
        bring_forward(running[pick or 0])
        sys.exit(0)
    if btn != 1:
        sys.exit(0)

    closed = [n for n in have if n not in running]
    closed.sort(key=lambda n: -used.get(str(n), 0))
    new = max(have) + 1
    target = new
    if closed:
        btn, pick = _alert(L["which_title"], L["which_text"], [L["open"], L["cancel"]],
                           [_label(L, n, used) for n in closed] + [L["new"]])
        if btn != 0:
            sys.exit(0)
        target = closed[pick] if pick is not None and pick < len(closed) else new
    os.makedirs(profile_dir(target), exist_ok=True)
    if not _take(target):      # opened elsewhere just now
        bring_forward(target)
        sys.exit(0)
    return _started(target)


def _started(n):
    _remember(n)
    os.environ["PARCELWIDGET_PROFILE"] = str(n)
    others = [x for x in profiles() if x != n and is_running(x)]
    os.environ["PARCELWIDGET_OTHERS"] = "1" if others else ""
    return n


def current():
    p = os.environ.get("PARCELWIDGET_PROFILE", "1")
    return int(p) if p.isdigit() else 1


def listen(on_show):
    """call on_show() (main thread) when another launch asks this copy to come forward"""
    global _observer
    if IS_WIN:
        import ctypes
        import threading
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        h = k32.CreateEventW(None, False, False, _event_name(current()))      # resets itself after each wait
        if not h:
            return

        def wait():
            while k32.WaitForSingleObject(h, 0xFFFFFFFF) == 0:
                try:
                    on_show()
                except Exception:
                    pass
        _observer = threading.Thread(target=wait, daemon=True)
        _observer.start()
        return
    import Foundation

    me = str(current())

    class _ShowObserver(Foundation.NSObject):
        def show_(self, note):
            if str(note.object()) == me:
                on_show()

    _observer = _ShowObserver.alloc().init()
    Foundation.NSDistributedNotificationCenter.defaultCenter() \
        .addObserver_selector_name_object_(_observer, "show:", SHOW, None)
