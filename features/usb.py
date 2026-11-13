"""USB: what's plugged in, which driver runs it, and whether that driver is current
(macOS and Windows; the Windows differences are at the end of this text).

At launch she lists the USB devices with their drivers, then looks online:
  - Apple's own drivers are part of macOS, so they're current when macOS is: she asks
    Software Update whether a newer macOS is out.
  - Other drivers: she looks the vendor up and searches the web for its driver. A version number
    found there is only a hint - she shows the links, she never installs anything.
  - A USB printer that isn't in the printer list: AirPrint printers need no driver; otherwise she
    looks for one on this Mac, then in Apple's printer driver catalog, and downloads it to
    ~/Downloads/Printer Drivers (you install it yourself).
AirPrint (Settings → Printers): the printer list grouped by physical printer, one-click AirPrint
setup, removing duplicate entries, picking the default (see airprint.py).
While running she rescans every 30 s; a newly plugged-in printer gets the printer treatment,
other devices just show up in the list.

Windows
  - Devices and drivers come from the registry (usbscan_win.py). The drivers that come with
    Windows (provider Microsoft) are current when Windows is: she asks Windows Update what's
    waiting. Makers publish their drivers on Windows Update too: a driver update waiting there
    for a plugged-in device is marked on that device. Other drivers: the web search, as on the Mac.
  - USB printers are set up by Windows itself when plugged in (plug and play, and without any
    driver for printers that speak IPP over USB). One that isn't in the printer list gets the
    links to its maker's driver and a button to Settings › Printers & scanners; nothing is downloaded.
  - Printers (Settings → Printers): winprint.py instead of airprint.py; "AirPrint" there is
    Windows' driverless printing (Microsoft IPP Class Driver).
In the data, "apple" means "comes with the system" and "macos" is the system's update status,
on both.

Report data (put into words by the page):
    startup: {"st": scanning|online|done, "n", "apple", "third", "macos": {"version", "update"},
              "newer": [names], "printers": [printer], "err"}
    printer: {"printer": printer}
printer = {"key", "name", "st": configured|airprint|local|found|downloading|downloaded|none|error,
           "queue", "mfg", "mdl", "driver": {"title", "date", "size"}, "done", "total", "file", "links", "err"}
"""
import threading
import time
import traceback

import plat
from core import IS_MAC, IS_WIN, load_memory, log, save_memory

from . import Feature

L = {
    "en": {"show": "Show USB Devices", "rescan": "Check Again", "settings": "USB Settings…",
           "air": "Printers & AirPrint…",
           "count": lambda n: "%d USB device%s" % (n, "" if n == 1 else "s") if n else "No USB devices"},
    "zh": {"show": "查看 USB 设备", "rescan": "重新检查", "settings": "USB 设置…", "air": "打印机与 AirPrint…",
           "count": lambda n: "%d 个 USB 设备" % n if n else "没有 USB 设备"},
}
RESCAN_EVERY = 30
SEARCH_MAX_AGE = 24 * 3600
PRINTERS_PANE = "ms-settings:printers" if IS_WIN else "x-apple.systempreferences:com.apple.Print-Scan-Settings.extension"
SUPPORTED = IS_MAC or IS_WIN


def _printing():
    """the module that knows this system's printer list (same functions in both)"""
    if IS_WIN:
        import winprint
        return winprint
    import airprint
    return airprint
QUIET_KINDS = ("hub", "billboard")     # plumbing: hidden unless "show hubs" is on


class USB(Feature):
    id = "usb"
    icon = "🔌"
    name = "USB"
    name_zh = "USB"

    def __init__(self, app):
        super().__init__(app)
        self.devices = []
        self.printers = {}       # key -> printer (see above)
        self.macos = None        # {"version", "updates", "checked"}
        self.online = {"st": "idle"}
        self.busy = False
        self.last_scan = 0
        self._lock = threading.Lock()
        self._dl_stop = False
        self._mem = {}           # bundle -> {"ts", "links", "hint"}: web search results
        self._reports = {}       # printer key -> its own report (a newly plugged-in printer)
        # AirPrint: groups = airprint.groups(); jobs: group key -> {"st": working|done|manual|error, "msg", "queue"}
        self._air_lock = threading.Lock()
        self.air = {"groups": None, "loading": False, "jobs": {}, "addr": {}, "found": []}

    def info(self):
        d = super().info()
        d["hover"] = d["hover"] and SUPPORTED
        d["available"] = SUPPORTED
        return d

    # ---------- lifecycle ----------
    def start(self):
        if not SUPPORTED:
            return
        self._mem = load_memory(self.id).get("search") or {}
        threading.Thread(target=self.run, args=("startup",), daemon=True).start()

    def tick(self, now):
        if not SUPPORTED or self.busy or now - self.last_scan < RESCAN_EVERY:
            return
        threading.Thread(target=self._rescan, daemon=True).start()

    def wake(self):
        self.last_scan = 0     # rescan soon after waking: things get (un)plugged while asleep

    # ---------- scanning ----------
    def _scan(self):
        import driverinfo
        if IS_WIN:
            import usbscan_win as usbscan
        else:
            import usbscan
        devs = usbscan.scan()
        for d in devs:
            try:
                v, p = driverinfo.vendor_names(d["vid"], d["pid"])
            except Exception:
                v, p = "", ""
            d["vendor_db"], d["product_db"] = v, p
            if d["vendor"].lower() in ("generic", "") and v:
                d["vendor"] = v
            if d.get("generic_name") and p:
                d["name"] = p       # Windows: "USB Composite Device" says less than the USB ID database
        self.last_scan = time.time()
        return devs

    def _rescan(self):
        if not self._lock.acquire(blocking=False):
            return
        try:
            old = {d["key"] for d in self.devices}
            devs = self._scan()
            new = [d for d in devs if d["key"] not in old]
            gone = old - {d["key"] for d in devs}
            if not new and not gone:
                return
            self.devices = devs
            for k in gone:
                self.printers.pop(k, None)
            for d in new:
                log("usb: plugged in %s (%s)" % (d["name"], d["vendor"]))
            self._annotate()
            for k in gone:
                log("usb: unplugged %s" % k)
            self.app.push_soon()
            self._air_changed()
        except Exception:
            log(traceback.format_exc())
        finally:
            self._lock.release()
        for d in new:
            if d["kind"] == "printer":
                self._printer_job(d, report=True)

    def run(self, kind="startup"):
        """the full check: scan, look online, sort out printers"""
        if not self._lock.acquire(blocking=False):
            return False
        app = self.app
        self.busy = True
        r = app.reports.add(self.id, kind, {"st": "scanning"}, hidden=(kind == "manual"))
        try:
            log("usb: check (%s) started" % kind)
            self.devices = self._scan()
            self._annotate()
            self._air_changed()
            app.reports.set(r, "st", "online")
            app.reports.set(r, "n", len(self.visible()))
            app.push_soon()
            self._online()
            self._annotate()
            ds = self.visible()
            drivers = [x for d in ds for x in d["drivers"]]
            data = {"st": "done", "n": len(ds),
                    "apple": len({x["bundle"] for x in drivers if x["apple"]}),
                    "third": len({x["bundle"] for x in drivers if not x["apple"]}),
                    "macos": {"version": (self.macos or {}).get("version"), "update": self._macos_update()},
                    "newer": sorted({x["name"] for x in drivers if x.get("check") == "maybe_newer"}),
                    "err": self.online.get("err")}
            for k, v in data.items():
                app.reports.set(r, k, v)
            log("usb: %d devices, %d Apple drivers, %d other drivers%s" % (
                data["n"], data["apple"], data["third"],
                ", macOS update %s" % data["macos"]["update"] if data["macos"]["update"] else ""))
        except Exception as e:
            log(traceback.format_exc())
            app.reports.set(r, "st", "done")
            app.reports.set(r, "err", str(e)[:160])
        finally:
            self.busy = False
            self._lock.release()
        printers = [d for d in self.devices if d["kind"] == "printer"]
        app.reports.set(r, "printers", [self._printer_job(d, report=False) for d in printers])
        if kind == "manual":
            app.reports.drop(r)
        else:
            app.reports.finish(r, hidden=False)
        app.push()
        return True

    def _online(self):
        import driverinfo
        self.online = {"st": "running"}
        errs = []
        try:
            u = driverinfo.windows_updates() if IS_WIN else driverinfo.macos_updates()
            self.macos = {"version": u.get("os"), "updates": u.get("updates", []), "checked": u.get("checked")}
        except Exception as e:
            errs.append("%s: %s" % ("Windows Update" if IS_WIN else "softwareupdate", str(e)[:80]))
            self.macos = {"version": driverinfo.windows_version() if IS_WIN else driverinfo.macos_version(),
                          "updates": None}
        self.macos["update"] = self._macos_update()      # for the page: what's waiting (None: nothing)
        for d in self.devices:
            for x in d["drivers"]:
                if x["apple"]:
                    continue
                m = self._mem.get(x["bundle"])
                if m and time.time() - m.get("ts", 0) < SEARCH_MAX_AGE:
                    continue
                vendor = d.get("vendor_db") or d["vendor"]
                q = "%s %s %s driver download" % (vendor, d.get("product_db") or d["name"], "Windows" if IS_WIN else "macOS")
                try:
                    links = driverinfo.search(q)
                    hint = driverinfo.newest_version_in([l["title"] for l in links])
                    self._mem[x["bundle"]] = {"ts": time.time(), "links": links, "hint": hint, "q": q}
                except Exception as e:
                    errs.append("search: %s" % str(e)[:80])
        save_memory(self.id, {"search": self._mem})
        self.online = {"st": "done", "checked": time.time(), "err": "; ".join(errs) or None}

    def _macos_update(self):
        """the system update that's waiting: its version (macOS), how many there are (Windows), or None"""
        ups = (self.macos or {}).get("updates") or []
        if IS_WIN:
            n = len([u for u in ups if not u.get("driver")])
            return str(n) if n else None
        os_up = [u for u in ups if u["title"].lower().startswith("macos")]
        return os_up[0]["version"] if os_up else None

    def _wu_drivers(self):
        """Windows: (vid, pid) of the devices Windows Update has a driver waiting for"""
        import re
        out = set()
        for u in (self.macos or {}).get("updates") or []:
            m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", str(u.get("hwid") or ""), re.I) if u.get("driver") else None
            if m:
                out.add((m.group(1).lower(), m.group(2).lower()))
        return out

    def _annotate(self):
        """add each driver's online status: apple_ok | apple_update | apple_unknown |
        ok | maybe_newer | unknown"""
        import driverinfo
        upd = self._macos_update()
        checked = self.macos is not None and self.macos.get("updates") is not None
        waiting = self._wu_drivers() if IS_WIN else ()
        for d in self.devices:
            for x in d["drivers"]:
                if (d["vid"], d["pid"]) in waiting:
                    x["links"], x["hint"], x["check"] = [], "wu", "maybe_newer"     # a driver for it is on Windows Update
                    continue
                if x["apple"]:
                    x["check"] = "apple_update" if upd else "apple_ok" if checked else "apple_unknown"
                    continue
                m = self._mem.get(x["bundle"]) or {}
                x["links"], x["hint"] = m.get("links") or [], m.get("hint")
                if x["hint"] and x.get("version") and driverinfo.vkey(x["hint"]) > driverinfo.vkey(x["version"]):
                    x["check"] = "maybe_newer"
                elif x["hint"] and x.get("version"):
                    x["check"] = "ok"
                else:
                    x["check"] = "unknown"

    def visible(self):
        if self.cfg.get("show_hubs"):
            return list(self.devices)
        return [d for d in self.devices if d["kind"] not in QUIET_KINDS]

    # ---------- printers ----------
    def _printer_job(self, dev, report):
        """work out what a USB printer needs; download its driver in the background if wanted.
        Returns the printer dict (also kept in self.printers and updated as it goes)."""
        p = {"key": dev["key"], "name": dev["name"], "vendor": dev["vendor"]}
        self.printers[dev["key"]] = p
        if IS_WIN:
            return self._printer_job_win(dev, p, report)
        import usbscan
        try:
            q = usbscan.is_configured(dev)
            if q:
                p.update(st="configured", queue=q)
                return p
            if dev.get("ipp_usb"):
                p.update(st="airprint")
                log("usb: printer %s isn't set up; AirPrint, no driver needed" % dev["name"])
                return self._printer_report(p, report)
            did = usbscan.device_id(dev)
            mfg = did.get("MFG") or dev["vendor"]
            mdl = did.get("MDL") or dev["name"]
            p.update(mfg=mfg, mdl=mdl)
            full = mdl if mdl.lower().startswith(mfg.lower()) else "%s %s" % (mfg, mdl)
            local = usbscan.local_driver(mfg, mdl)
            if local:
                p.update(st="local", driver={"title": local["name"]})
                log("usb: printer %s isn't set up; its driver is already on this Mac" % mdl)
                return self._printer_report(p, report)
            import driverinfo
            drv = driverinfo.find_printer_driver(mfg, mdl)
            if not drv:
                p.update(st="none", links=driverinfo.search("%s printer driver macOS" % full))
                log("usb: no driver found for printer %s" % full)
                return self._printer_report(p, report)
            p.update(st="found", driver={"title": drv["title"], "date": drv["date"], "size": drv["size"]})
            log("usb: printer %s needs %s (%s, %d MB)" % (mdl, drv["title"], drv["date"], drv["size"] // 1000000))
            if self.cfg.get("auto_download", True):
                self._start_download(p, drv)
            return self._printer_report(p, report)
        except Exception as e:
            log(traceback.format_exc())
            p.update(st="error", err=str(e)[:160])
            return p

    def _printer_job_win(self, dev, p, report):
        """Windows sets USB printers up by itself; say so, or point to the maker's driver"""
        import driverinfo
        import winprint
        try:
            q = winprint.queue_for(dev)
            for _ in range(3 if report else 0):         # just plugged in: give Windows a moment to add it
                if q or self.app.closing:
                    break
                time.sleep(5)
                q = winprint.queue_for(dev)
            if q:
                p.update(st="configured", queue=q)
                return p
            if dev.get("ipp_usb"):
                p.update(st="airprint")
                log("usb: printer %s isn't in the printer list; it needs no driver" % dev["name"])
                return self._printer_report(p, report)
            full = dev["name"] if dev["name"].lower().startswith((dev.get("vendor") or "").lower()) \
                else "%s %s" % (dev.get("vendor") or "", dev["name"])
            p.update(st="none", mdl=dev["name"], links=driverinfo.search("%s printer driver Windows" % full.strip()))
            log("usb: printer %s isn't in the printer list" % full.strip())
            return self._printer_report(p, report)
        except Exception as e:
            log(traceback.format_exc())
            p.update(st="error", err=str(e)[:160])
            return p

    def _printer_report(self, p, report):
        if report:
            r = self.app.reports.add(self.id, "printer", {"printer": p}, live=p["st"] == "downloading")
            self._reports[p["key"]] = r
        self.app.push_soon()
        return p

    def _report_of(self, p):
        return self._reports.pop(p["key"], None)

    def _start_download(self, p, drv):
        import driverinfo
        p.update(st="downloading", done=0, total=drv["size"])
        self._dl_stop = False

        def progress(done, total):
            p["done"], p["total"] = done, total or p.get("total")
            self.app.push_soon()

        def work():
            try:
                f = driverinfo.download_printer_driver(drv, progress, lambda: self._dl_stop or self.app.closing)
                p.update(st="downloaded", file=f)
                log("usb: downloaded %s" % f)
            except InterruptedError:
                p.update(st="found", done=0)
                log("usb: download of %s cancelled" % drv["title"])
            except Exception as e:
                log(traceback.format_exc())
                p.update(st="error", err=str(e)[:160])
            r = self._report_of(p)
            if r:
                self.app.reports.finish(r, hidden=False)
            self.app.push()
        threading.Thread(target=work, daemon=True).start()

    # ---------- AirPrint ----------
    def _air_refresh(self, discover=False):
        if not SUPPORTED:
            return
        with self._air_lock:
            self._air_refresh_locked(discover)

    def _air_refresh_locked(self, discover):
        airprint = _printing()
        self.air["loading"] = True
        self.app.push_soon()
        try:
            if discover:
                self.air["found"] = airprint.discover()
            self.air["groups"] = airprint.groups(self.devices, found=self.air["found"])
        except Exception:
            log(traceback.format_exc())
        finally:
            self.air["loading"] = False
            self.app.push_soon()

    def _air_changed(self):
        """devices changed: refresh the printer groups if the page has asked for them"""
        if self.air["groups"] is not None:
            threading.Thread(target=self._air_refresh, daemon=True).start()

    def _air_group(self, key):
        return next((g for g in self.air["groups"] or [] if g["key"] == key), None)

    def _air_job(self, key, label, work, alias=None):
        """run a printer-list change in the background; its outcome shows by the printer"""
        airprint = _printing()
        job = self.air["jobs"][key] = {"st": "working", "what": label}
        if alias:
            self.air["jobs"][alias] = job
        self.app.push_soon()

        def run():
            try:
                res = work() or {}
                job.update(st="manual" if res.get("manual") else "done", queue=res.get("queue"),
                           already=res.get("already", False))
                log("airprint: %s %s: %s" % (label, key, res.get("queue") or ("manual" if res.get("manual") else "ok")))
            except airprint.SetupError as e:
                job.update(st="error", msg=str(e))
                log("airprint: %s %s failed: %s" % (label, key, e))
            except Exception as e:
                log(traceback.format_exc())
                job.update(st="error", msg=str(e)[:160])
            self._air_refresh()
        threading.Thread(target=run, daemon=True).start()
        return True

    def api_printers(self, discover=False):
        threading.Thread(target=self._air_refresh, args=(bool(discover),), daemon=True).start()
        return True

    def api_airprint(self, key, make_default=True):
        """set the printer up with AirPrint (key: a group key, or a USB device key)"""
        airprint = _printing()
        if not SUPPORTED:
            return False
        g = self._air_group(key)
        alias = None
        if not g:
            alias = key
            dev = next((d for d in self.devices if d["key"] == key), None)
            gs = airprint.groups(self.devices)
            self.air["groups"] = gs
            g = dev and next((x for x in gs if x["via"] == "usb" and x["connected"] and x["name"] == dev["name"]), None)
        if not g or not g.get("can_setup"):
            return False
        return self._air_job(g["key"], "setup", lambda: airprint.setup(g, make_default=bool(make_default)),
                             alias=alias)

    def api_airprint_address(self, text, make_default=False):
        airprint = _printing()
        if not SUPPORTED or not str(text or "").strip():
            return False
        return self._air_job("addr", "add", lambda: airprint.add_address(str(text), make_default=bool(make_default)))

    def api_remove_extra(self, key):
        """take a printer's duplicate entries out of the printer list (the page asked first)"""
        airprint = _printing()
        g = self._air_group(key)
        if not g or not g.get("best") or not g.get("extra"):
            return False
        names = list(g["extra"])
        return self._air_job(key, "tidy", lambda: airprint.remove(names) or {"queue": g["best"]})

    def api_make_default(self, key):
        airprint = _printing()
        g = self._air_group(key)
        if not g or not g.get("best"):
            return False
        return self._air_job(key, "default", lambda: airprint.make_default(g["best"]) or {"queue": g["best"]})

    def api_test_page(self, key):
        airprint = _printing()
        g = self._air_group(key)
        if not g or not g.get("best"):
            return False
        return self._air_job(key, "test", lambda: airprint.test_page(g["best"]) and {"queue": g["best"]})

    def api_open_printers(self):
        self.app.open_settings("printers")
        return True

    def api_add_printer_window(self):
        plat.open_path(_printing().ADD_PRINTER)
        return True

    # ---------- the page ----------
    def state(self):
        ds = self.visible()
        return {"devices": ds, "printers": self.printers, "busy": self.busy, "online": self.online,
                "macos": self.macos, "last_scan": self.last_scan, "mac": IS_MAC, "os": "win" if IS_WIN else "mac",
                "hidden": len(self.devices) - len(ds), "air": self.air}

    def api_check(self):
        if self.busy:
            return False
        threading.Thread(target=self.run, args=("manual",), daemon=True).start()
        return True

    def api_download(self, key):
        p = self.printers.get(key)
        if not p or p.get("st") not in ("found", "error"):
            return False
        dev = next((d for d in self.devices if d["key"] == key), None)
        if not dev:
            return False
        threading.Thread(target=self._printer_job, args=(dev, True), daemon=True).start()
        return True

    def api_cancel_download(self):
        self._dl_stop = True
        return True

    def api_open_file(self, key):
        p = self.printers.get(key) or {}
        if p.get("file"):
            plat.open_path(p["file"])
            return True
        return False

    def api_reveal_downloads(self):
        import driverinfo
        import os
        os.makedirs(driverinfo.DOWNLOADS, exist_ok=True)
        plat.open_path(driverinfo.DOWNLOADS)
        return True

    def api_printer_settings(self):
        plat.open_path(PRINTERS_PANE)
        return True

    def menu(self, lang):
        if not SUPPORTED:
            return None
        T = L.get(lang, L["en"])
        return [{"title": T["count"](len(self.visible())), "info": True},
                {"sep": True},
                {"title": T["show"], "key": "usb:show"},
                {"title": T["rescan"], "key": "usb:check", "enabled": not self.busy},
                {"title": T["air"], "key": "usb:printers"},
                {"sep": True},
                {"title": T["settings"], "key": "usb:settings"}]

    def handle(self, action, arg=""):
        if action == "show":
            self.app.show_window()
            self.app.page_call("openFeature('usb')")
        elif action == "check":
            self.api_check()
        elif action == "printers":
            self.app.open_settings("printers")
        elif action == "settings":
            self.app.open_settings("usb")

    def get_settings(self):
        import driverinfo
        return {"auto_download": bool(self.cfg.get("auto_download", True)),
                "show_hubs": bool(self.cfg.get("show_hubs", False)), "folder": driverinfo.DOWNLOADS}

    def save_settings(self, s):
        for k in ("auto_download", "show_hubs"):
            if k in s:
                self.cfg[k] = bool(s[k])
        self.app.push_soon()
