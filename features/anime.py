"""Anime: which shows of the season got a new episode today, from Mikan Project (mikanani.me).

Mikan's home page lists the season's shows by day of the week (plus movies and OVAs), each with
the date its latest episode came out. That is the same list ani-rss uses for its schedule; she
reads it every `every` minutes (and when you open her 📺 balloon), with no account and no extra
program.

What she keeps is a week of days, Monday to Sunday: each day holds the shows that got a new
episode on that date. When the same weekday comes round again, last week's day is cleared and
filled anew - so the panel always shows the last 7 days, and "today" is today's slot plus the
shows still expected today (on today's schedule, no new episode yet).

    every day      a summary in her balloon (from `summary_at` o'clock, once a day)
    optionally     a balloon when a new episode comes out (Settings → 📺 Anime)

Kept in memory.json ("anime"): the 7 days, the season and the last schedule, so a restart shows
the panel at once.
"""
import datetime
import html as _html
import re
import threading
import time
import urllib.request

import plat
from core import load_memory, log, save_config, save_memory

from . import Feature

HOSTS = ["https://mikanani.me", "https://mikanime.tv"]
EVERYS = [30, 60, 120, 240]         # minutes between checks
HOURS = list(range(0, 24))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ParcelWidget"
MOVIE, OVA = 7, 8                   # Mikan's "days" after Sunday..Saturday

L = {
    "en": {"open": "Today's anime", "refresh": "Check now", "settings": "Anime Settings…", "site": "Open Mikan"},
    "zh": {"open": "今日新番", "refresh": "立即刷新", "settings": "追番设置…", "site": "打开蜜柑计划"},
}


# ---------------- reading Mikan ----------------
def _text(s):
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def mikan_to_weekday(d):
    """Mikan counts 0 = Sunday ... 6 = Saturday; Python 0 = Monday ... 6 = Sunday"""
    return (int(d) - 1) % 7 if 0 <= int(d) <= 6 else int(d)


def parse_home(page, host=HOSTS[0]):
    """Mikan's home page -> {"season": "2026 秋季番组", "shows": [{id, title, url, cover, day, updated}]}
    day: 0 Monday ... 6 Sunday, 7 movie, 8 OVA. updated: "YYYY-MM-DD" (or "")."""
    host = host.rstrip("/")
    m = re.search(r'class="sk-col date-text">(.*?)<span', page, re.S)
    season = _text(m.group(1)) if m else ""
    shows, seen = [], set()
    blocks = re.split(r'<div class="sk-bangumi"', page)[1:]
    for b in blocks:
        dm = re.match(r'\s*data-dayofweek="(\d+)"', b)
        if not dm:
            continue
        day = mikan_to_weekday(dm.group(1))
        for li in re.findall(r"<li>(.*?)</li>", b, re.S):
            a = re.search(r'<a href="(/Home/Bangumi/(\d+))"[^>]*class="an-text"[^>]*title="([^"]*)"', li)
            if not a:
                continue
            path, bid, title = a.group(1), a.group(2), _html.unescape(a.group(3)).strip()
            if bid in seen:
                continue
            seen.add(bid)
            img = re.search(r'data-src="([^"?]+)', li)
            dt = re.search(r'class="date-text">\s*(\d{4})/(\d{1,2})/(\d{1,2})', li)
            shows.append({
                "id": bid, "title": title, "url": host + path, "day": day,
                "cover": (host + img.group(1) + "?width=120&height=120&format=webp") if img else "",
                "updated": "%04d-%02d-%02d" % tuple(int(x) for x in dt.groups()) if dt else "",
            })
    return {"season": season, "shows": shows}


def fetch_home(host, timeout=20):
    req = urllib.request.Request(host.rstrip("/") + "/", headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------------- a week of days ----------------
def week_dates(today):
    """the date each weekday stands for now: the last 7 days, today included. {0: "2026-11-16", ...}"""
    return {w: (today - datetime.timedelta(days=(today.weekday() - w) % 7)).isoformat() for w in range(7)}


def roll(days, today):
    """clear the days that belong to last week (same weekday, 7+ days ago). True if any was cleared."""
    want, changed = week_dates(today), False
    for w in range(7):
        d = days.get(str(w))
        if not d or d.get("date") != want[w]:
            days[str(w)] = {"date": want[w], "items": {}}
            changed = changed or bool(d and d.get("items"))
    return changed


def merge(days, shows, today):
    """put each show whose latest episode came out in the last 7 days on that day.
    Returns the ids added to today (new since the last check)."""
    roll(days, today)
    want, added = week_dates(today), []
    by_date = {v: str(w) for w, v in want.items()}
    for s in shows:
        w = by_date.get(s.get("updated") or "")
        if w is None:
            continue
        items = days[w]["items"]
        if s["id"] not in items:
            if s["updated"] == today.isoformat():
                added.append(s["id"])
        items[s["id"]] = {k: s[k] for k in ("title", "url", "cover", "day")}
    return added


def stats(days, schedule, today):
    """today's numbers and the week's"""
    tw = today.weekday()
    done = days.get(str(tw), {}).get("items", {})
    sched = [s for s in schedule if s.get("day") == tw]
    pending = [s for s in sched if s["id"] not in done]
    return {"scheduled": len(sched), "updated": len(done), "pending": len(pending),
            "week": sum(len(d.get("items") or {}) for d in days.values()),
            "per_day": [len(days.get(str(w), {}).get("items") or {}) for w in range(7)],
            "season": len([s for s in schedule if s.get("day", 9) <= 6])}


class Anime(Feature):
    id = "anime"
    icon = "📺"
    name = "Anime"
    name_zh = "追番"
    hover = True

    def __init__(self, app):
        super().__init__(app)
        self.days = {}             # "0".."6" (Monday..Sunday) -> {"date", "items": {id: show}}
        self.schedule = []         # this season's shows, as Mikan lists them (with their weekday)
        self.season = ""
        self.last = 0              # last check (time)
        self.err = ""
        self.busy = False
        self._today = None
        self._lock = threading.Lock()

    # ---------- settings ----------
    def every(self):
        v = self.cfg.get("every", 60)
        return v if v in EVERYS else 60

    def host(self):
        v = self.cfg.get("host")
        return v if v in HOSTS else HOSTS[0]

    def summary_at(self):
        v = self.cfg.get("summary_at", 9)
        return v if v in HOURS else 9

    def _c(self, k, default):
        v = self.cfg.get(k)
        return default if v is None else v

    # ---------- start / schedule ----------
    def start(self):
        mem = load_memory(self.id)
        self.days = mem.get("days") or {}
        self.schedule = mem.get("schedule") or []
        self.season = mem.get("season") or ""
        self.last = mem.get("ts") or 0
        self._today = datetime.date.today()
        roll(self.days, self._today)
        if time.time() - self.last > self.every() * 60:
            self.refresh()
        else:
            self._summary_due()

    def stop(self):
        pass

    def wake(self):
        self.tick(time.time(), wake=True)

    def tick(self, now, wake=False):
        today = datetime.date.today()
        if today != self._today:               # midnight: last week's day makes room for today
            self._today = today
            roll(self.days, today)
            self._save()
            self.app.push_soon()
        if now - self.last > self.every() * 60:
            self.refresh()
        else:
            self._summary_due()

    def refresh(self, manual=False):
        with self._lock:
            if self.busy:
                return
            self.busy = True
        self.app.push_soon()
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual):
        first = not self.schedule
        try:
            got = parse_home(fetch_home(self.host()), self.host())
            if not got["shows"]:
                raise ValueError("no shows on the page")
            today = datetime.date.today()
            self._today = today
            added = merge(self.days, got["shows"], today)
            self.schedule = [dict(id=s["id"], title=s["title"], url=s["url"], cover=s["cover"], day=s["day"],
                                  updated=s["updated"]) for s in got["shows"]]
            self.season = got["season"] or self.season
            self.err = ""
            st = stats(self.days, self.schedule, today)
            log("anime: %d shows, %d out today (%d of %d on today's schedule), %d this week" % (
                len(self.schedule), st["updated"], st["scheduled"] - st["pending"], st["scheduled"], st["week"]))
            if added and not first and not manual and self._c("notify_new", False):
                items = self.days[str(today.weekday())]["items"]
                self.app.reports.add(self.id, "new", {"titles": [items[i]["title"] for i in added][:8],
                                                      "n": len(added)}, live=False)
        except Exception as e:
            self.err = str(e)[:160] or type(e).__name__
            log("anime: check failed %r" % self.err)
        finally:
            self.last = time.time()
            self.busy = False
            self._save()
            self._summary_due()
            self.app.push_soon()

    def _save(self):
        save_memory(self.id, {"ts": self.last, "days": self.days, "schedule": self.schedule,
                              "season": self.season, "summary": self.cfg.get("summary_date")})

    # ---------- the daily summary ----------
    def _summary_due(self):
        if not self._c("summary", True) or not self.schedule:
            return
        today = datetime.date.today().isoformat()
        if self.cfg.get("summary_date") == today or datetime.datetime.now().hour < self.summary_at():
            return
        self.cfg["summary_date"] = today
        save_config(self.app.cfg)
        for r in list(self.app.reports.items):      # yesterday's, if you never looked
            if r["feature"] == self.id and r["kind"] == "daily":
                self.app.reports.drop(r)
        self.app.reports.add(self.id, "daily", self.summary(), live=False)

    def summary(self):
        today = datetime.date.today()
        tw = today.weekday()
        items = self.days.get(str(tw), {}).get("items", {})
        st = stats(self.days, self.schedule, today)
        pending = [s["title"] for s in self.schedule if s.get("day") == tw and s["id"] not in items]
        return dict(st, date=today.isoformat(), weekday=tw, season=self.season,
                    done=[v["title"] for v in items.values()][:8], todo=pending[:8])

    # ---------- her balloon ----------
    def api_opened(self):
        if time.time() - self.last > 600:
            self.refresh(manual=True)
        return True

    def api_refresh(self):
        self.refresh(manual=True)
        return True

    def api_open(self, url):
        if isinstance(url, str) and any(url.startswith(h + "/") for h in HOSTS):
            plat.open_url(url)
        return True

    def state(self):
        today = self._today or datetime.date.today()
        tw = today.weekday()
        want = week_dates(today)
        days = []
        for w in range(7):
            d = self.days.get(str(w)) or {}
            items = (d.get("items") or {}) if d.get("date") == want[w] else {}
            days.append({"w": w, "date": want[w], "items": [dict(v, id=k) for k, v in items.items()]})
        done = self.days.get(str(tw), {}).get("items", {}) if self.days.get(str(tw), {}).get("date") == want[tw] else {}
        todo = [dict(s) for s in self.schedule if s.get("day") == tw and s["id"] not in done]
        return {"busy": self.busy, "err": self.err, "last": self.last, "season": self.season, "today": tw,
                "days": days, "todo": todo, "stats": stats(self.days, self.schedule, today),
                "host": self.host()}

    # ---------- menus and settings ----------
    def menu(self, lang):
        T = L.get(lang, L["en"])
        return [{"title": T["open"], "key": "anime:show"}, {"title": T["refresh"], "key": "anime:refresh"},
                {"title": T["site"], "key": "anime:site"}, {"title": T["settings"], "key": "anime:settings"}]

    def handle(self, action, arg=""):
        if action == "settings":
            self.app.open_settings("anime")
        elif action == "refresh":
            self.refresh(manual=True)
        elif action == "site":
            plat.open_url(self.host())
        else:
            self.app.show_window()
            self.app.page_call("openFeature('anime')")

    def get_settings(self):
        return {"every": self.every(), "everys": EVERYS, "host": self.host(), "hosts": HOSTS,
                "summary": bool(self._c("summary", True)), "summary_at": self.summary_at(),
                "notify_new": bool(self._c("notify_new", False)), "last": self.last, "err": self.err}

    def save_settings(self, s):
        if s.get("every") in EVERYS:
            self.cfg["every"] = s["every"]
        if s.get("host") in HOSTS and s["host"] != self.cfg.get("host"):
            self.cfg["host"] = s["host"]
            self.last = 0                       # a different site: look again soon
        if s.get("summary_at") in HOURS:
            self.cfg["summary_at"] = s["summary_at"]
        for k in ("summary", "notify_new"):
            if k in s:
                self.cfg[k] = bool(s[k])
