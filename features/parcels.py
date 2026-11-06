"""Parcels: find tracking numbers in Gmail and read their status on parcelsapp.com.

Runs once at launch (with a report you confirm), then automatically every `every_min`
minutes between `start` and `end` (default 09:00-19:00 every 90 min). An automatic check
only shows a report if something changed.

Sleep: no automatic checks while the computer is asleep. When it wakes up she checks once,
quietly (a report only if something changed) - unless the last check is still current
(no scheduled time has passed since), then she does nothing.

Network errors (e.g. Wi-Fi not back yet): an automatic check is retried quietly up to
NET_RETRIES times, NET_RETRY_MIN minutes apart; only the last failure is reported.

Memory: every full check saves its time and result (memory.json). At launch, if the last check
is still current (no scheduled time has passed since), she shows that result instead of checking
again; the report then has data["cached"] = the time of that check.

Report data (put into words by the page):
    mail:  {"st": reading|done|off|error, "n", "total", "found": [{number, carrier, new}], "err"}
    track: {"st": running|done, "n", "total", "cur"}
    sum:   {"new", "delivered", "moved", "errors": [numbers], "checked": n}
    err:   text, if the whole run failed
"""
import datetime
import os
import subprocess
import threading
import time
import traceback

from core import APP_DIR, get_password, load_memory, log, save_memory, set_password
from db import DB
from tracker import BROWSERS, DEFAULT_BROWSER
from tracking_parser import guess_carrier

from . import Feature

# browsers Playwright can download by itself; others must be installed by the user
AUTO_INSTALL = {"chromium": "chromium", "firefox": "firefox", "webkit": "webkit"}

NET_RETRIES = 3        # quiet retries of an automatic check that failed for lack of network
NET_RETRY_MIN = 3
WAKE_DELAY = 20        # seconds after waking up before checking: Wi-Fi needs a moment
AUTO_KINDS = ("scheduled", "wake", "retry")   # automatic checks: a report only if something changed


def _is_net_error(e):
    """no network / DNS / timeouts - worth retrying, unlike a wrong password"""
    import socket
    if isinstance(e, (socket.gaierror, socket.timeout, TimeoutError, ConnectionError)):
        return True
    text = str(e).lower()
    return any(w in text for w in ("nodename", "name or service", "network is unreachable", "timed out",
                                   "connection reset", "connection refused", "connection aborted"))

L = {
    "en": {"check": "Check Now", "checking": "Checking…", "show": "Show Packages", "add": "Add Tracking Number…",
           "settings": "Parcel Settings…",
           "count": lambda n, d: ("%d package%s" % (n, "" if n == 1 else "s") + (" · %d delivered" % d if d else ""))
           if n else "No packages",
           "next": lambda t: "Next check " + t},
    "zh": {"check": "立即检查", "checking": "检查中…", "show": "查看快递", "add": "添加单号…", "settings": "快递设置…",
           "count": lambda n, d: ("%d 个快递" % n + ("，%d 个已送达" % d if d else "")) if n else "暂无快递",
           "next": lambda t: "下次检查 " + t},
}


def _hm(s, default):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return default


class Parcels(Feature):
    id = "parcels"
    icon = "📦"
    name = "Parcels"
    name_zh = "快递"

    def __init__(self, app):
        super().__init__(app)
        self.db = DB(os.path.join(APP_DIR, "shipments.db"))
        self.busy = False
        self.last_run = None
        self.next_due = None
        self.mail_error = None
        self.net_failed = False   # the last mail read failed for lack of network
        self.net_tries = 0        # quiet retries used for the current failure
        self.retry_due = False    # next_due is a retry, not a scheduled time
        self.wake_at = None       # time.time() when to do the after-wake check
        self.installing = None
        self.refreshing = set()
        self._lock = threading.Lock()
        self._track_lock = threading.Lock()
        self._pw = {}      # Gmail address -> app password, read from the Keychain once

    def password(self, addr):
        """The Keychain is read once per address: every read of another program's item can make
        macOS ask for permission, and the pages ask for the state many times a minute."""
        if not addr:
            return ""
        if addr not in self._pw:
            self._pw[addr] = get_password(addr)
        return self._pw[addr]

    # ---------- schedule ----------
    def start(self):
        mem = load_memory(self.id)
        ts = mem.get("ts")
        if ts:
            self.last_run = ts
            due = self.next_slot(datetime.datetime.fromtimestamp(ts))
            if due and due > datetime.datetime.now():
                # the last check is still current: report what it found, check again at the next slot
                self.next_due = due
                log("startup: last check %s is still current, next at %s" % (
                    time.strftime("%H:%M", time.localtime(ts)), due.strftime("%H:%M")))
                self.app.reports.add(self.id, "startup", dict(mem.get("data") or {}, cached=ts), live=False)
                return

        def first():
            time.sleep(2)
            self.run("startup")
        threading.Thread(target=first, daemon=True).start()

    def next_slot(self, after):
        """The next automatic check after `after` (datetime): start, start+every, ... up to end."""
        c = self.cfg
        st, en = _hm(c.get("start"), 9 * 60), _hm(c.get("end"), 19 * 60)
        every = max(15, int(c.get("every_min") or 90))
        if en < st:
            en = st
        for day in range(8):
            d = (after + datetime.timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
            m = st
            while m <= en:
                t = d + datetime.timedelta(minutes=m)
                if t > after:
                    return t
                m += every
        return None

    def sleep(self):
        self.wake_at = None

    def wake(self):
        self.wake_at = time.time() + WAKE_DELAY

    def current(self):
        """the last check is still current: no scheduled time has passed since"""
        if not self.last_run:
            return False
        due = self.next_slot(datetime.datetime.fromtimestamp(self.last_run))
        return bool(due and due > datetime.datetime.now())

    def tick(self, now):
        if self.busy:
            return
        if self.wake_at:
            if now < self.wake_at:
                return             # the after-wake check comes first
            self.wake_at = None
            if self.current():
                self.next_due = self.next_slot(datetime.datetime.fromtimestamp(self.last_run))
                log("wake: last check %s is still current, staying quiet (next at %s)" % (
                    time.strftime("%H:%M", time.localtime(self.last_run)),
                    self.next_due.strftime("%H:%M") if self.next_due else "-"))
                return
            self.run("wake")
            return
        if self.next_due is None:
            self.next_due = self.next_slot(datetime.datetime.now())
        if self.next_due and datetime.datetime.now() >= self.next_due:
            kind = "retry" if self.retry_due else "scheduled"
            self.next_due = self.next_slot(datetime.datetime.now())
            self.run(kind)

    # ---------- a full check, reported in her balloon ----------
    def run(self, kind):
        """kind: startup | manual | scheduled | wake | retry"""
        if not self._lock.acquire(blocking=False):
            return False
        app = self.app
        r = None
        try:
            self.busy = True
            log("check (%s) started" % kind)
            before = {i["number"]: i for i in self.db.active()}
            # an automatic check stays hidden unless it finds something
            r = app.reports.add(self.id, kind, {"mail": None, "track": None, "sum": None},
                                hidden=(kind in AUTO_KINDS))
            new_nums = self._scan_mail(r)
            checked = self._track(r=r)
            self._finish(r, before, new_nums, checked)
        except Exception as e:
            log(traceback.format_exc())
            if r is not None:
                app.reports.set(r, "err", str(e)[:160])
                app.reports.finish(r, hidden=False)
        finally:
            self.busy = False
            self.next_due = self.next_slot(datetime.datetime.now())
            self.retry_due = False
            if self.net_failed and kind in AUTO_KINDS and self.net_tries <= NET_RETRIES:
                retry = datetime.datetime.now() + datetime.timedelta(minutes=NET_RETRY_MIN)
                if not self.next_due or retry < self.next_due:
                    self.next_due, self.retry_due = retry, True
            self._lock.release()
            app.push()
        return True

    def check_now(self):
        if self.busy:
            return False
        threading.Thread(target=self.run, args=("manual",), daemon=True).start()
        return True

    def _finish(self, r, before, new_nums, checked):
        after = {i["number"]: i for i in self.db.active()}
        s = {"new": [n for n in new_nums if n in after], "delivered": [], "moved": [], "errors": [],
             "checked": len(checked)}
        for n in checked:
            it, old = after.get(n), before.get(n)
            if not it:
                continue
            if it.get("error"):
                if it["error"] != (old or {}).get("error"):   # the same old error isn't news
                    s["errors"].append(n)
            elif it["delivered"] and not (old or {}).get("delivered"):
                s["delivered"].append(n)
            elif old and (it.get("status") or "") != (old.get("status") or "") and n not in s["new"]:
                s["moved"].append(n)
        mail = r["data"].get("mail") or {}
        changed = bool(s["new"] or s["delivered"] or s["moved"] or s["errors"]) or mail.get("st") == "error"
        self.app.reports.set(r, "sum", s)
        net = mail.get("st") == "error" and self.net_failed
        auto = r["kind"] in AUTO_KINDS
        if not net:
            # remember when and what, so a restart (or wake) soon after doesn't check again;
            # a check that couldn't reach the network isn't a result worth remembering
            self.last_run = time.time()
            save_memory(self.id, {"ts": self.last_run, "kind": r["kind"],
                                  "data": {k: r["data"].get(k) for k in ("mail", "track", "sum")}})
        if net and auto:
            if r["kind"] != "retry":
                self.net_tries = 0            # a new series of retries
            self.net_tries += 1
            if self.net_tries <= NET_RETRIES:
                log("no network: retry %d/%d in %d min" % (self.net_tries, NET_RETRIES, NET_RETRY_MIN))
                self.app.reports.drop(r)      # quiet: try again soon
                return
            log("no network after %d retries: giving up until the next scheduled check" % NET_RETRIES)
        elif not net:
            self.net_tries = 0
        log("check (%s) done: %d new, %d delivered, %d moved, %d errors, %d looked up" % (
            r["kind"], len(s["new"]), len(s["delivered"]), len(s["moved"]), len(s["errors"]), s["checked"]))
        if auto and not changed:
            self.app.reports.drop(r)          # nothing new: stay quiet
        else:
            self.app.reports.finish(r, hidden=False)

    def _scan_mail(self, r):
        """-> tracking numbers that are new to the widget"""
        reports, c = self.app.reports, self.cfg
        addr = c.get("gmail_address")
        pw = self.password(addr)
        if not addr or not pw:
            reports.set(r, "mail", {"st": "off"})
            return []
        from mail_scanner import scan_gmail
        reports.set(r, "mail", {"st": "reading", "n": 0, "total": 0, "found": []})

        def progress(done, total, found):
            reports.set(r, "mail", {"st": "reading", "n": done, "total": total,
                                    "found": [{"number": f["number"], "carrier": f["carrier"]} for f in found]})
        try:
            items = scan_gmail(addr, pw, days=int(c.get("scan_days", 14)), log=log, progress=progress)
            self.mail_error = None
            self.net_failed = False
        except Exception as e:
            self.mail_error = str(e)[:160]
            self.net_failed = _is_net_error(e)
            log("gmail error: %r" % e)
            reports.set(r, "mail", {"st": "error", "err": self.mail_error})
            return []
        found, new = [], []
        for i in items:
            is_new = self.db.add(i["number"], i["carrier"], i["title"], "email")
            found.append({"number": i["number"], "carrier": i["carrier"], "new": is_new})
            if is_new:
                new.append(i["number"])
        total = (r["data"].get("mail") or {}).get("total", 0)
        reports.set(r, "mail", {"st": "done", "n": total, "total": total, "found": found})
        log("Gmail scan done, %d new" % len(new))
        return new

    def _track(self, only=None, r=None):
        """-> the numbers that were looked up"""
        # one browser profile can't be opened twice, so tracking runs one batch at a time
        with self._track_lock:
            return self._track_locked(only, r)

    def _track_locked(self, only, r):
        from tracker import ParcelsAppTracker
        reports = self.app.reports
        nums = list(only) if only else [x["number"] for x in self.db.to_check()]
        if not nums:
            if r:
                reports.set(r, "track", {"st": "done", "n": 0, "total": 0})
            return []
        if r:
            reports.set(r, "track", {"st": "running", "n": 0, "total": len(nums), "cur": nums[0]})
        c = self.cfg
        browser = c.get("browser", DEFAULT_BROWSER)
        t = ParcelsAppTracker(os.path.join(APP_DIR, "browser-profile"),
                              headless=bool(c.get("headless", True)), browser=browser, log=log)
        missing, done = [], []

        def on_start(i, num):
            if r:
                reports.set(r, "track", {"st": "running", "n": i, "total": len(nums), "cur": num})

        def on_result(num, res):
            done.append(num)
            err = res.get("error")
            if err:
                if err.startswith("browser_missing"):
                    missing.append(err)
                self.db.set_error(num, err)
            else:
                self.db.update_status(num, res["status"], res["location"], res["event_time"], res["delivered"])
            self.app.push_soon()

        t.track_many(nums, on_result, should_stop=lambda: self.app.closing or self.app.asleep, on_start=on_start)
        if r:
            reports.set(r, "track", {"st": "done", "n": len(done), "total": len(nums)})
        if missing and browser in AUTO_INSTALL:
            threading.Thread(target=self.install_browser, args=(browser,), daemon=True).start()
        return done

    def install_browser(self, browser):
        """Download a Playwright browser (chromium / firefox / webkit) in the background."""
        if self.installing:
            return
        self.installing = browser
        r = self.app.reports.add(self.id, "install", {"browser": browser})
        try:
            # Playwright's own driver (works in the packaged app too, where there is no `python -m`)
            from playwright._impl._driver import compute_driver_executable, get_driver_env
            p = subprocess.run([*compute_driver_executable(), "install", AUTO_INSTALL[browser]],
                               capture_output=True, text=True, timeout=900, env=get_driver_env())
            log(p.stdout[-500:] + p.stderr[-500:])
            ok = p.returncode == 0
        except Exception as e:
            log("install error %r" % e)
            ok = False
        self.installing = None
        self.app.reports.set(r, "ok", ok)
        self.app.reports.finish(r)
        if ok:
            self.check_now()

    def track_one(self, number):
        if number in self.refreshing:
            return False

        def go():
            self.refreshing.add(number)
            self.app.push()
            try:
                self._track(only={number})
            except Exception as ex:
                log("track one error %r" % ex)
            finally:
                self.refreshing.discard(number)
                self.app.push()
        threading.Thread(target=go, daemon=True).start()
        return True

    # ---------- what the pages can call: api.feature("parcels", "<name>", ...) ----------
    def api_check(self):
        return self.check_now()

    def api_confirm(self, number):
        self.db.archive(number)
        self.app.push()
        return True

    def api_unarchive(self, number):
        self.db.unarchive(number)
        self.app.push()
        return True

    def api_archived(self):
        return self.db.archived()

    def api_add(self, number, title=""):
        number = "".join(str(number).split()).upper()
        if len(number) < 8:
            return {"ok": False, "msg": "too_short"}
        if not self.db.add(number, guess_carrier(number), title, "manual"):
            self.db.unarchive(number)
        self.track_one(number)
        return {"ok": True, "number": number}

    def api_refresh_one(self, number):
        return self.track_one(number)

    def api_delete(self, number):
        self.db.delete(number)
        self.app.push()
        return True

    # ---------- state, menu, settings ----------
    def configured(self):
        a = self.cfg.get("gmail_address")
        return bool(self.password(a))

    def state(self):
        items = self.db.active()
        return {
            "items": items,
            "busy": self.busy,
            "refreshing": sorted(self.refreshing),
            "last_run": self.last_run,
            "next_check": self.next_due.timestamp() if self.next_due else None,
            "configured": self.configured(),
            "mail_error": self.mail_error,
        }

    def counts(self):
        items = self.db.active()
        return len(items), sum(1 for i in items if i["delivered"])

    def menu(self, lang):
        T = L.get(lang, L["en"])
        n, d = self.counts()
        info = T["checking"] if self.busy else T["count"](n, d)
        items = [{"title": info, "info": True}]
        if self.next_due and not self.busy:
            items.append({"title": T["next"](self.next_due.strftime("%H:%M")), "info": True})
        items += [
            {"sep": True},
            {"title": T["check"], "key": "parcels:check", "enabled": not self.busy, "shortcut": "r"},
            {"title": T["show"], "key": "parcels:show"},
            {"title": T["add"], "key": "parcels:add"},
            {"sep": True},
            {"title": T["settings"], "key": "parcels:settings"},
        ]
        return items

    def handle(self, action, arg=""):
        app = self.app
        if action == "check":
            self.check_now()
        elif action == "show":
            app.show_window()
            app.page_call("openFeature('parcels')")
        elif action == "add":
            app.show_window()
            app.page_call("openFeature('parcels', 'add')")
        elif action == "settings":
            app.open_settings("parcels")

    def get_settings(self):
        s = dict(self.cfg)
        s["has_password"] = self.configured()
        s["browsers"] = list(BROWSERS)
        return s

    def save_settings(self, s):
        c = self.cfg
        c["gmail_address"] = (s.get("gmail_address") or "").strip()
        c["scan_days"] = max(1, int(s.get("scan_days") or 14))
        c["headless"] = bool(s.get("headless", True))
        if s.get("browser") in BROWSERS:
            c["browser"] = s["browser"]
        for k, d in (("start", "09:00"), ("end", "19:00")):
            v = str(s.get(k) or d)
            c[k] = v if _hm(v, None) is not None else d
        c["every_min"] = max(15, int(s.get("every_min") or 90))
        pw = (s.get("app_password") or "").replace(" ", "")
        if pw and c["gmail_address"]:
            set_password(c["gmail_address"], pw)
            self._pw[c["gmail_address"]] = pw
        self.next_due = self.next_slot(datetime.datetime.now())
