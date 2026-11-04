"""System monitor: CPU, RAM and network traffic, drawn as candlestick charts.

A sampler thread reads the values once a second (psutil works on macOS and Windows) and
keeps the last hour. The page asks for candles: each candle covers `period` seconds and
shows the open / high / low / close of the samples in it, like a stock chart.
"""
import collections
import threading
import time

from . import Feature

KEEP = 3600   # seconds of samples kept

L = {
    "en": {"show": "Show Monitor", "settings": "Monitor Settings…"},
    "zh": {"show": "查看系统状态", "settings": "系统状态设置…"},
}
PERIODS = [5, 10, 30, 60]


def candles(samples, key, period, count):
    """samples: [(ts, {key: value})] -> up to `count` newest candles
    [{"t": start, "o", "h", "l", "c"}], oldest first."""
    out = []
    cur = None
    for ts, v in samples:
        x = v.get(key)
        if x is None:
            continue
        b = int(ts // period) * period
        if cur is None or cur["t"] != b:
            if cur:
                out.append(cur)
            cur = {"t": b, "o": x, "h": x, "l": x, "c": x}
        else:
            cur["h"] = max(cur["h"], x)
            cur["l"] = min(cur["l"], x)
            cur["c"] = x
    if cur:
        out.append(cur)
    return out[-count:]


class SysMon(Feature):
    id = "sysmon"
    icon = "📊"
    name = "System"
    name_zh = "系统状态"

    def __init__(self, app):
        super().__init__(app)
        self.samples = collections.deque(maxlen=KEEP)
        self.lock = threading.Lock()
        self.sys_info = {}
        self.ok = True

    def start(self):
        threading.Thread(target=self._sample_loop, daemon=True).start()

    def _sample_loop(self):
        try:
            import psutil
        except Exception:
            self.ok = False
            return
        psutil.cpu_percent(None)                     # the first reading is always 0
        last = psutil.net_io_counters()
        last_t = time.time()
        while not self.app.closing:
            time.sleep(1)
            try:
                now = time.time()
                net = psutil.net_io_counters()
                dt = max(0.2, now - last_t)
                vm = psutil.virtual_memory()
                v = {
                    "cpu": psutil.cpu_percent(None),
                    "ram": vm.percent,
                    "down": max(0, net.bytes_recv - last.bytes_recv) / dt,   # bytes / s
                    "up": max(0, net.bytes_sent - last.bytes_sent) / dt,
                }
                last, last_t = net, now
                with self.lock:
                    self.samples.append((now, v))
                    self.sys_info = {"ram_used": vm.total - vm.available, "ram_total": vm.total,
                                 "cores": psutil.cpu_count() or 0}
            except Exception:
                time.sleep(5)

    # api.feature("sysmon", "candles", period, count)
    def api_candles(self, period=None, count=36):
        period = int(period or self.cfg.get("period") or 10)
        count = max(5, min(120, int(count or 36)))
        with self.lock:
            s = list(self.samples)
            info = dict(self.sys_info)
        last = s[-1][1] if s else {}
        return {
            "ok": self.ok,
            "period": period,
            "now": last,
            "info": info,
            "series": {k: candles(s, k, period, count) for k in ("cpu", "ram", "down", "up")},
        }

    def state(self):
        return {"period": int(self.cfg.get("period") or 10), "colors": self.cfg.get("colors", "auto"), "ok": self.ok}

    def menu(self, lang):
        T = L.get(lang, L["en"])
        return [{"title": T["show"], "key": "sysmon:show"},
                {"sep": True},
                {"title": T["settings"], "key": "sysmon:settings"}]

    def handle(self, action, arg=""):
        if action == "show":
            self.app.show_window()
            self.app.page_call("openFeature('sysmon')")
        elif action == "settings":
            self.app.open_settings("sysmon")

    def get_settings(self):
        return {"period": int(self.cfg.get("period") or 10), "colors": self.cfg.get("colors", "auto"),
                "periods": PERIODS}

    def save_settings(self, s):
        p = int(s.get("period") or 10)
        self.cfg["period"] = p if p in PERIODS else 10
        if s.get("colors") in ("auto", "green_up", "red_up"):
            self.cfg["colors"] = s["colors"]
