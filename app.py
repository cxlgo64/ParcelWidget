"""Parcel Widget — a small macOS desktop widget that tracks packages.

- Every hour: scan Gmail for tracking numbers -> read the latest event for each on parcelsapp.com
- Shows the first 3 active shipments, expandable to all
- Delivered shipments turn green; confirm with ✅ to archive
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback

import webview

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from db import DB  # noqa: E402
from tracker import BROWSERS, DEFAULT_BROWSER  # noqa: E402
from tracking_parser import guess_carrier  # noqa: E402

APP_DIR = os.path.expanduser("~/Library/Application Support/ParcelWidget")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "widget.log")
KEYRING_SERVICE = "ParcelWidget-Gmail"

DEFAULT_CONFIG = {
    "gmail_address": "",
    "interval_minutes": 60,
    "scan_days": 14,
    "headless": True,        # run the tracking browser invisibly
    "browser": DEFAULT_BROWSER,
    "always_on_top": False,
    "size_preset": "14",
    "lang": "en",
}

# window width (px), max height (px) and UI zoom per screen size
SIZE_PRESETS = {
    "13": {"label": '13"', "w": 248, "h": 360, "zoom": 0.74},
    "14": {"label": '14"', "w": 262, "h": 390, "zoom": 0.78},
    "15": {"label": '15"', "w": 276, "h": 420, "zoom": 0.82},
    "16": {"label": '16"', "w": 292, "h": 450, "zoom": 0.87},
    "ext": {"label": "External", "w": 320, "h": 500, "zoom": 0.95},
}
# browsers Playwright can download by itself; others must be installed by the user
AUTO_INSTALL = {"chromium": "chromium", "firefox": "firefox", "webkit": "webkit"}


def preset(cfg):
    return SIZE_PRESETS.get(str(cfg.get("size_preset")), SIZE_PRESETS["14"])


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg)
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_password(address):
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, address) or ""
    except Exception:
        return ""


def set_password(address, pw):
    import keyring  # stored in the macOS Keychain, never in a plain file
    keyring.set_password(KEYRING_SERVICE, address, pw)


def later(fn, delay=0.05):
    """Run fn on another thread shortly. Window calls made directly inside a js_api
    callback can deadlock on macOS, because pywebview still has to send the return
    value back to the page."""
    def run():
        time.sleep(delay)
        try:
            fn()
        except Exception as ex:
            log("window op error %r" % ex)
    threading.Thread(target=run, daemon=True).start()


class Engine:
    def __init__(self):
        self.cfg = load_config()
        self.db = DB(os.path.join(APP_DIR, "shipments.db"))
        self.window = None
        self.busy = False
        self.last_run = None
        self.message = None       # {"code": ..., "arg": ...}; translated in the UI
        self.mail_message = None  # Gmail problems stay visible after a run
        self.installing = None
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._track_lock = threading.Lock()
        self.refreshing = set()
        self.closing = False

    # ---------- background loop ----------
    def loop(self):
        time.sleep(2)
        while not self.closing:
            self.run_once()
            interval = max(10, int(self.cfg.get("interval_minutes", 60))) * 60
            self._wake.wait(interval)
            self._wake.clear()

    def trigger(self):
        self._wake.set()

    def run_once(self):
        if not self._lock.acquire(blocking=False):
            return
        try:
            self.busy = True
            self.push()
            self._scan_mail()
            self._track_all()
            self.last_run = time.time()
            self.message = None
        except Exception as e:
            self.message = {"code": "error", "arg": str(e)[:120]}
            log(traceback.format_exc())
        finally:
            self.busy = False
            self._lock.release()
            self.push()

    def _scan_mail(self):
        addr = self.cfg.get("gmail_address")
        pw = get_password(addr) if addr else ""
        if not addr or not pw:
            self.mail_message = {"code": "no_gmail"}
            return
        from mail_scanner import scan_gmail
        self.message = {"code": "reading_gmail"}
        self.push()
        try:
            items = scan_gmail(addr, pw, days=int(self.cfg.get("scan_days", 14)), log=log)
            self.mail_message = None
        except Exception as e:
            self.mail_message = {"code": "gmail_error", "arg": str(e)[:120]}
            log("gmail error: %r" % e)
            return
        new = sum(self.db.add(i["number"], i["carrier"], i["title"], "email") for i in items)
        log("Gmail scan done, %d new" % new)

    def _track_all(self, only=None):
        # one browser profile can't be opened twice, so tracking runs one batch at a time
        with self._track_lock:
            self._track_all_locked(only)

    def _track_all_locked(self, only):
        from tracker import ParcelsAppTracker
        nums = list(only) if only else [r["number"] for r in self.db.to_check()]
        if not nums:
            return
        self.message = {"code": "checking", "arg": len(nums)}
        self.push()
        browser = self.cfg.get("browser", DEFAULT_BROWSER)
        t = ParcelsAppTracker(
            os.path.join(APP_DIR, "browser-profile"),
            headless=bool(self.cfg.get("headless", True)),
            browser=browser,
            log=log,
        )
        missing = []

        def on_result(num, res):
            err = res.get("error")
            if err:
                if err.startswith("browser_missing"):
                    missing.append(err)
                self.db.set_error(num, err)
            else:
                self.db.update_status(num, res["status"], res["location"],
                                      res["event_time"], res["delivered"])
            self.push()

        t.track_many(nums, on_result, should_stop=lambda: self.closing)
        if missing and browser in AUTO_INSTALL:
            self.install_browser(browser)

    def install_browser(self, browser):
        """Download a Playwright browser (chromium / firefox / webkit) in the background."""
        if self.installing:
            return
        self.installing = browser
        self.message = {"code": "installing", "arg": browser}
        self.push()
        try:
            r = subprocess.run([sys.executable, "-m", "playwright", "install", AUTO_INSTALL[browser]],
                               capture_output=True, text=True, timeout=900)
            log(r.stdout[-500:] + r.stderr[-500:])
            ok = r.returncode == 0
        except Exception as e:
            log("install error %r" % e)
            ok = False
        self.installing = None
        self.message = {"code": "installed" if ok else "install_failed", "arg": browser}
        self.push()
        if ok:
            self.trigger()

    def push(self):
        # don't talk to the window while it is closing, or both sides wait on each other
        if self.window and not self.closing:
            try:
                self.window.evaluate_js("window.onBackendUpdate && window.onBackendUpdate()")
            except Exception:
                pass


class Api:
    """Methods callable from the page as window.pywebview.api.xxx"""

    def __init__(self, engine):
        self.e = engine

    # ---------- data ----------
    def get_state(self):
        e, c = self.e, self.e.cfg
        return {
            "items": e.db.active(),
            "busy": e.busy,
            "refreshing": sorted(e.refreshing),
            "last_run": e.last_run,
            "message": e.message or e.mail_message,
            "configured": bool(c.get("gmail_address") and get_password(c["gmail_address"])),
            "on_top": bool(c.get("always_on_top")),
            "size_preset": str(c.get("size_preset", "14")),
            "zoom": preset(c)["zoom"],
            "max_h": preset(c)["h"],
            "presets": [{"key": k, "label": v["label"]} for k, v in SIZE_PRESETS.items()],
            "lang": c.get("lang", "en"),
        }

    def get_archived(self):
        return self.e.db.archived()

    def confirm(self, number):
        self.e.db.archive(number)
        return True

    def unarchive(self, number):
        self.e.db.unarchive(number)
        return True

    def add_manual(self, number, title=""):
        number = "".join(number.split()).upper()
        if len(number) < 8:
            return {"ok": False, "msg": "too_short"}
        added = self.e.db.add(number, guess_carrier(number), title, "manual")
        if not added:
            self.e.db.unarchive(number)
        threading.Thread(target=self._track_one, args=(number,), daemon=True).start()
        return {"ok": True}

    def _track_one(self, number):
        self.e.refreshing.add(number)
        self.e.push()
        try:
            self.e._track_all(only={number})
        except Exception as ex:
            log("track one error %r" % ex)
        finally:
            self.e.refreshing.discard(number)
        self.e.push()

    def refresh_now(self):
        self.e.trigger()
        return True

    def refresh_one(self, number):
        if number in self.e.refreshing:
            return False
        threading.Thread(target=self._track_one, args=(number,), daemon=True).start()
        return True

    # ---------- settings ----------
    def get_settings(self):
        c = dict(self.e.cfg)
        c["has_password"] = bool(c.get("gmail_address") and get_password(c["gmail_address"]))
        c["browsers"] = list(BROWSERS)
        return c

    def save_settings(self, s):
        c = self.e.cfg
        c["gmail_address"] = (s.get("gmail_address") or "").strip()
        c["interval_minutes"] = int(s.get("interval_minutes") or 60)
        c["scan_days"] = int(s.get("scan_days") or 14)
        c["headless"] = bool(s.get("headless", True))
        if s.get("browser") in BROWSERS:
            c["browser"] = s["browser"]
        pw = (s.get("app_password") or "").replace(" ", "")
        if pw and c["gmail_address"]:
            set_password(c["gmail_address"], pw)
        save_config(c)
        self.e.trigger()
        return True

    def set_lang(self, lang):
        self.e.cfg["lang"] = "zh" if lang == "zh" else "en"
        save_config(self.e.cfg)
        return self.e.cfg["lang"]

    def set_on_top(self, value):
        c = self.e.cfg
        c["always_on_top"] = bool(value)
        save_config(c)
        later(lambda: setattr(self.e.window, "on_top", c["always_on_top"]))
        return c["always_on_top"]

    def set_size(self, key):
        if key not in SIZE_PRESETS:
            return None
        self.e.cfg["size_preset"] = key
        save_config(self.e.cfg)
        p = SIZE_PRESETS[key]
        return {"zoom": p["zoom"], "max_h": p["h"]}

    # ---------- window ----------
    def fit(self, css_height):
        """Resize the window so it is exactly as tall as the content (up to the preset max)."""
        p = preset(self.e.cfg)
        h = int(min(p["h"], max(30, round(float(css_height) * p["zoom"]))))
        w = p["w"]

        def do():
            win = self.e.window
            if abs((win.height or 0) - h) <= 1 and abs((win.width or 0) - w) <= 1:
                return
            try:
                from webview.window import FixPoint
                win.resize(w, h, fix_point=FixPoint.NORTH | FixPoint.WEST)  # keep top-left in place
            except Exception:
                x, y = win.x, win.y
                win.resize(w, h)
                win.move(x, y)
        later(do, 0)
        return h

    def get_pos(self):
        return [self.e.window.x, self.e.window.y]

    def move(self, x, y):
        # called repeatedly while dragging; window.move is thread-safe
        try:
            self.e.window.move(int(x), int(y))
        except Exception as ex:
            log("move error %r" % ex)
        return True

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def minimize(self):
        later(self.e.window.minimize)

    def quit(self):
        self.e.closing = True

        def _close():
            try:
                self.e.window.destroy()
            except Exception:
                pass
            time.sleep(2)
            os._exit(0)  # fallback: force exit (incl. a tracking browser) after 2 s
        later(_close, 0.2)
        return True


def main():
    engine = Engine()
    api = Api(engine)
    p = preset(engine.cfg)
    win = webview.create_window(
        "Parcel Widget",
        os.path.join(HERE, "ui", "index.html"),
        js_api=api,
        width=p["w"],
        height=60,               # the page resizes the window to fit its content
        min_size=(200, 30),
        frameless=True,
        easy_drag=False,
        on_top=bool(engine.cfg.get("always_on_top")),
        background_color="#1c1c1e",
    )
    engine.window = win
    threading.Thread(target=engine.loop, daemon=True).start()

    def on_closing():
        engine.closing = True

    win.events.closing += on_closing
    webview.start()
    os._exit(0)  # exit right away once the window is gone; all data is already saved


if __name__ == "__main__":
    main()
