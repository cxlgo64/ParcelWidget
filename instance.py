"""Which copy of the widget this is, decided before anything else starts (macOS).

Each copy is like an account: copy 1 keeps its data in the usual folder, copy 2, 3, ... in
Profiles/<n> next to it, each with its own settings, Gmail and parcels. A running copy holds a
lock on locks/<n>.lock (released by the system if it crashes).

At launch (choose()):
  - nothing open      -> start the copy used last, no questions
  - one already open  -> ask: go to the open one (it comes to the front), or open another one
                         (a copy that isn't open, or a new one)
  - started at login (launchd) while one is open -> quietly do nothing
The open copy is brought forward with a system-wide notification (listen()).
"""
import fcntl
import json
import os
import sys
import time

IS_MAC = sys.platform == "darwin"
if sys.platform == "win32":
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
        with open(_lock_path(n), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    except OSError:
        return False


def _take(n):
    """hold copy n's lock; False if another process has it"""
    global _lock_file
    os.makedirs(os.path.dirname(_lock_path(n)), exist_ok=True)
    f = open(_lock_path(n), "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
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


def bring_forward(n):
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
            if IS_MAC:
                bring_forward(n)
            sys.exit(0)
        return _started(n)
    if not IS_MAC:
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
    if os.environ.get("XPC_SERVICE_NAME") == LAUNCHD_LABEL:
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
    import Foundation

    me = str(current())

    class _ShowObserver(Foundation.NSObject):
        def show_(self, note):
            if str(note.object()) == me:
                on_show()

    _observer = _ShowObserver.alloc().init()
    Foundation.NSDistributedNotificationCenter.defaultCenter() \
        .addObserver_selector_name_object_(_observer, "show:", SHOW, None)
