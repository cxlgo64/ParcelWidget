"""Parcel Widget: a desktop character who does little jobs for you.

- The window is just the character and her speech balloon (ui/index.html).
- Her jobs are features (features/): parcel tracking, a system monitor, poke, ... Each one
  runs at launch and reports in her balloon; you confirm the report and it goes on in the
  background on its own schedule, speaking up again only when something changes.
- Idle: hover over her for a button per feature; right-click her (or use the menu bar icon)
  for the menu (menus.py); detailed settings live in a separate window (ui/settings.html).
"""
import os
import sys
import threading
import time
import traceback

import webview

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import (APP_DIR, IS_MAC, SIZE_PRESETS, SKINS_DIR, UI_DIR, later, list_skins, load_config,  # noqa: E402,F401
                  log, preset, save_config)
from features import make_features  # noqa: E402
from reports import Reports  # noqa: E402


class App:
    def __init__(self):
        self.cfg = load_config()
        self.window = None            # the character
        self.settings_window = None   # the settings popup, while open
        self.menubar = None           # menu bar icon (macOS), see menubar.py
        self.visible = True
        self.closing = False
        self.skin_job = None          # custom skin being generated: {"step", "total", "label", "error", "id", "done"}
        self._skin_stop = False
        self._wake = threading.Event()
        self._push_at = 0
        self._push_timer = None
        self.reports = Reports(on_change=self.push_soon)
        self.features = make_features(self)
        if not any(s["id"] == self.cfg.get("skin") for s in list_skins()):
            skins = list_skins()
            self.cfg["skin"] = skins[0]["id"] if skins else ""

    def feature(self, fid):
        return next((f for f in self.features if f.id == fid), None)

    # ---------- background ----------
    def loop(self):
        for f in self.features:
            try:
                f.start()
            except Exception:
                log(traceback.format_exc())
        while not self.closing:
            now = time.time()
            for f in self.features:
                try:
                    f.tick(now)
                except Exception:
                    log(traceback.format_exc())
            self._wake.wait(15)
            self._wake.clear()

    # ---------- windows ----------
    def show_window(self):
        self.visible = True
        later(self.window.show, 0)

    def hide_window(self):
        self.visible = False
        later(self.window.hide, 0)

    def toggle_window(self):
        self.hide_window() if self.visible else self.show_window()

    def page_call(self, js, delay=0.3):
        """Run JS in the character's page (from a worker thread)."""
        def go():
            if self.window and not self.closing:
                self.window.evaluate_js(js)
        later(go, delay)

    def open_settings(self, tab="general"):
        tab = tab.replace("'", "")
        if self.menubar:
            from menubar import activate
            activate()
        w = self.settings_window
        if w:
            later(w.show, 0)
            later(lambda: w.evaluate_js("openTab('%s')" % tab), 0.1)
            return
        lang = self.cfg.get("lang", "en")
        w = webview.create_window(
            "设置 · 快递小组件" if lang == "zh" else "Parcel Widget Settings",
            os.path.join(UI_DIR, "settings.html") + "#" + tab,
            js_api=self.api, width=520, height=600, min_size=(440, 420))
        self.settings_window = w

        def closed():
            self.settings_window = None
        w.events.closed += closed

    def quit(self):
        self.closing = True

        def _close():
            for w in (self.settings_window, self.window):
                try:
                    w and w.destroy()
                except Exception:
                    pass
            time.sleep(2)
            os._exit(0)  # fallback: force exit (incl. a tracking browser) after 2 s
        later(_close, 0.2)
        return True

    # ---------- tell the pages something changed ----------
    def push_soon(self):
        """push(), at most a few times a second (progress callbacks fire often)."""
        now = time.time()
        if now - self._push_at >= 0.4:
            self.push()
        elif not self._push_timer:
            def go():
                self._push_timer = None
                self.push()
            self._push_timer = threading.Timer(0.4, go)
            self._push_timer.daemon = True
            self._push_timer.start()

    def push(self):
        self._push_at = time.time()
        if self.menubar:
            try:
                self.menubar.set_count(*self.feature("parcels").counts())
            except Exception as ex:
                log("menubar error %r" % ex)
        # don't talk to the windows while closing, or both sides wait on each other
        if self.closing:
            return
        for w in (self.window, self.settings_window):
            if w:
                try:
                    w.evaluate_js("window.onBackendUpdate && window.onBackendUpdate()")
                except Exception:
                    pass


class Api:
    """Methods callable from the pages as window.pywebview.api.xxx (both windows share it)."""

    def __init__(self, app):
        self.a = app

    # ---------- state ----------
    def get_state(self):
        a, c = self.a, self.a.cfg
        p = preset(c)
        return {
            "lang": c.get("lang", "en"),
            "on_top": bool(c.get("always_on_top")),
            "size_preset": str(c.get("size_preset", "14")),
            "zoom": p["zoom"], "max_h": p["h"], "base_w": p["w"],
            "presets": [{"key": k, "label": v["label"]} for k, v in SIZE_PRESETS.items()],
            "skin": self._skin(),
            "skin_side": c.get("skin_side", "right"),
            "skin_job": a.skin_job,
            "features": [f.info() for f in a.features],
            "f": {f.id: f.state() for f in a.features},
            "reports": a.reports.visible(),
        }

    def feature(self, fid, method, *args):
        """Call a feature's api_<method> (see features/)."""
        f = self.a.feature(fid)
        fn = getattr(f, "api_" + method, None) if f else None
        if not fn:
            return {"error": "unknown"}
        return fn(*args)

    def ack_report(self, rid):
        return self.a.reports.ack(rid)

    # ---------- settings ----------
    def get_settings(self):
        c = self.a.cfg
        out = {"general": {"lang": c.get("lang", "en"), "on_top": bool(c.get("always_on_top")),
                           "size_preset": str(c.get("size_preset", "14")),
                           "skin": c.get("skin", ""), "skin_side": c.get("skin_side", "right")}}
        for f in self.a.features:
            out[f.id] = f.get_settings()
        return out

    def save_settings(self, section, values):
        f = self.a.feature(section)
        if not f:
            return False
        f.save_settings(values or {})
        save_config(self.a.cfg)
        self.a.push()
        return True

    def set_lang(self, lang):
        self.a.cfg["lang"] = "zh" if lang == "zh" else "en"
        save_config(self.a.cfg)
        self.a.push()
        return self.a.cfg["lang"]

    def set_on_top(self, value):
        c = self.a.cfg
        c["always_on_top"] = bool(value)
        save_config(c)
        later(lambda: setattr(self.a.window, "on_top", c["always_on_top"]))
        self.a.push()
        return c["always_on_top"]

    def set_size(self, key):
        if key not in SIZE_PRESETS:
            return None
        self.a.cfg["size_preset"] = key
        save_config(self.a.cfg)
        self.a.push()
        p = SIZE_PRESETS[key]
        return {"zoom": p["zoom"], "max_h": p["h"], "base_w": p["w"]}

    def open_settings(self, tab="general"):
        self.a.open_settings(tab)
        return True

    # ---------- skins ----------
    def _skin(self):
        sid = self.a.cfg.get("skin") or ""
        for s in list_skins():
            if s["id"] == sid:
                return s
        return None

    def get_skins(self):
        return [{"id": s["id"], "name": s.get("name", s["id"]), "name_zh": s.get("name_zh", ""),
                 "thumb": s.get("thumb", ""), "custom": bool(s.get("custom"))} for s in list_skins()]

    def set_skin(self, skin_id=None, side=None):
        c = self.a.cfg
        if skin_id and any(s["id"] == skin_id for s in list_skins()):
            c["skin"] = skin_id
        if side in ("left", "right"):
            c["skin_side"] = side
        save_config(c)
        self.a.push()
        return {"skin": self._skin(), "skin_side": c["skin_side"]}

    def delete_skin(self, skin_id):
        """Only generated (custom) skins can be deleted."""
        import shutil
        for s in list_skins():
            if s["id"] == skin_id and s.get("custom"):
                shutil.rmtree(os.path.join(SKINS_DIR, skin_id), ignore_errors=True)
                if self.a.cfg.get("skin") == skin_id:
                    self.a.cfg["skin"] = next((x["id"] for x in list_skins()), "")
                    save_config(self.a.cfg)
                self.a.push()
                return True
        return False

    # ---------- custom skins (generated with an image API, see skinmaker/) ----------
    def get_skin_gen(self):
        from skinmaker import DEFAULT_PROVIDER, PROVIDERS, get_key
        g = self.a.cfg.get("skin_gen") or {}
        return {
            "providers": [dict(p.info(), has_key=bool(get_key(p.id))) for p in PROVIDERS.values()],
            "provider": g.get("provider") or DEFAULT_PROVIDER,
            "models": g.get("models") or {},
            "base_urls": g.get("base_urls") or {},
            "job": self.a.skin_job,
        }

    def pick_ref_image(self):
        """Native file picker; returns the path and a small preview."""
        import base64
        import io
        win = self.a.settings_window or self.a.window
        res = win.create_file_dialog(webview.FileDialog.OPEN, file_types=("Images (*.png;*.jpg;*.jpeg;*.webp)",))
        if not res:
            return None
        path = res[0] if isinstance(res, (list, tuple)) else res
        try:
            from PIL import Image
            im = Image.open(path)
            im.thumbnail((96, 96))
            buf = io.BytesIO()
            im.convert("RGBA").save(buf, "PNG")
            return {"path": path, "preview": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
                    "name": os.path.basename(path)}
        except Exception as ex:
            return {"error": str(ex)[:120]}

    def start_skin_gen(self, opts):
        a = self.a
        if a.skin_job and not a.skin_job.get("done"):
            return {"ok": False, "msg": "busy"}
        from skinmaker import get_key, get_provider, set_key
        pid = opts.get("provider")
        try:
            p = get_provider(pid)
        except Exception:
            return {"ok": False, "msg": "provider"}
        key = (opts.get("key") or "").strip()
        if key:
            set_key(pid, key)
        key = key or get_key(pid)
        if not key:
            return {"ok": False, "msg": "no_key"}
        name = (opts.get("name") or "").strip()
        desc = (opts.get("desc") or "").strip()
        ref_path = opts.get("ref_path") or ""
        if not desc and not ref_path:
            return {"ok": False, "msg": "no_desc"}
        g = a.cfg.setdefault("skin_gen", {})
        g["provider"] = pid
        g.setdefault("models", {})[pid] = (opts.get("model") or "").strip()
        g.setdefault("base_urls", {})[pid] = (opts.get("base_url") or "").strip()
        save_config(a.cfg)
        ref = None
        if ref_path:
            with open(ref_path, "rb") as f:
                ref = f.read()
        a._skin_stop = False
        a.skin_job = {"step": 0, "total": 11, "label": "base", "error": None, "id": None, "done": False,
                      "provider": p.name, "failed": [], "name": name or "My Skin"}
        threading.Thread(target=self._run_skin_gen, daemon=True,
                         args=(name or "My Skin", desc, pid, key, ref, g["models"][pid], g["base_urls"][pid])).start()
        a.push()
        return {"ok": True}

    def _run_skin_gen(self, name, desc, pid, key, ref, model, base_url):
        from skinmaker import Cancelled, make_skin
        a, job = self.a, self.a.skin_job
        # she reports it like any other job (put into words by the page: FEATURES.skin)
        r = a.reports.add("skin", "make", {"job": dict(job)})

        def progress(done, total, label):
            job.update(step=done, total=total, label=label)
            a.reports.set(r, "job", dict(job))
        try:
            sid, failed = make_skin(SKINS_DIR, name, desc, pid, key, ref, model or None, base_url or None,
                                    log=lambda m: log("skin: %s" % m), progress=progress,
                                    should_stop=lambda: a._skin_stop or a.closing)
            job.update(id=sid, failed=sorted(failed))
            a.cfg["skin"] = sid
            save_config(a.cfg)
        except Cancelled:
            job["error"] = "cancelled"
        except Exception as ex:
            log("skin generation failed: %s" % traceback.format_exc())
            job["error"] = str(ex)[:300]
        job["done"] = True
        a.reports.set(r, "job", dict(job))
        a.reports.finish(r)
        a.push()

    def cancel_skin_gen(self):
        self.a._skin_stop = True
        return True

    def clear_skin_job(self):
        if self.a.skin_job and self.a.skin_job.get("done"):
            self.a.skin_job = None
        return True

    # ---------- the character's window ----------
    def fit(self, css_width, css_height):
        """Resize the window to the page's layout (CSS px x zoom), keeping her feet where
        they are: the bottom corner on her side stays put while the balloon opens."""
        a = self.a
        z = preset(a.cfg)["zoom"]
        w = int(max(60, round(float(css_width) * z)))
        h = int(max(60, round(float(css_height) * z)))

        def do():
            win = a.window
            if os.environ.get("PARCELWIDGET_DEBUG"):
                log("fit %dx%d (window %sx%s)" % (w, h, win.width, win.height))
            if abs((win.height or 0) - h) <= 1 and abs((win.width or 0) - w) <= 1:
                return
            from webview.window import FixPoint
            side = FixPoint.EAST if a.cfg.get("skin_side", "right") == "right" else FixPoint.WEST
            win.resize(w, h, fix_point=FixPoint.SOUTH | side)
        later(do, 0)
        return h

    def get_pos(self):
        return [self.a.window.x, self.a.window.y]

    def move(self, x, y):
        # called repeatedly while dragging; window.move is thread-safe
        try:
            self.a.window.move(int(x), int(y))
        except Exception as ex:
            log("move error %r" % ex)
        return True

    def context_menu(self):
        """Right-click on her: the same menu as the menu bar icon."""
        if self.a.menubar:
            self.a.menubar.popup()
            return True
        return False

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def hide(self):
        if self.a.menubar:
            self.a.hide_window()
        else:
            later(self.a.window.minimize)

    def quit(self):
        return self.a.quit()


def main():
    app = App()
    api = Api(app)
    app.api = api
    p = preset(app.cfg)
    win = webview.create_window(
        "Parcel Widget",
        os.path.join(UI_DIR, "index.html"),
        js_api=api,
        width=int(p["w"] * 0.6),
        height=int(p["w"] * 0.7),   # the page resizes the window to fit her and her balloon
        min_size=(60, 60),
        frameless=True,
        easy_drag=False,
        on_top=bool(app.cfg.get("always_on_top")),
        transparent=True,
    )
    app.window = win
    threading.Thread(target=app.loop, daemon=True).start()

    def on_closing():
        app.closing = True

    win.events.closing += on_closing

    # live in the menu bar instead of the Dock (macOS)
    started = None
    if IS_MAC:
        try:
            import menubar
            from PyObjCTools import AppHelper
            menubar.hide_dock_icon()
            app.menubar = menubar.MenuBar(app)

            def started():
                AppHelper.callAfter(app.menubar.install)
                app.push()
        except Exception as ex:
            app.menubar = None
            log("menu bar icon unavailable: %r" % ex)
    webview.start(started)
    os._exit(0)  # exit right away once the window is gone; all data is already saved


if __name__ == "__main__":
    main()
