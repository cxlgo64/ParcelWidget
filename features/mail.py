"""Mail: a first look at what's in your inboxes (Apple Mail - on Windows the classic Outlook -
and Outlook through Microsoft if you sign in).

She reads the newest inbox mail (subject and sender, nothing is changed or marked read) and
sorts it: important / the rest / can skip (see mailread.screen()). Clicking a message opens it
in Mail or in Outlook on the web.

Quiet by design
  - Nothing happens until you open Mail yourself once (her ✉️ button or the menu): before
    that she doesn't touch Mail, so macOS never asks about it out of the blue.
  - After that she looks every `every` minutes in the background. An automatic look only
    speaks up when new important unread mail arrived (Settings → Mail can turn that off).
  - Microsoft sign-in is optional, and only ever shown when you open Mail: automatic looks
    never ask for it. When Microsoft wants you to sign in again, she waits until you open
    Mail, then shows the sign-in code in her balloon.
  - Automatic looks don't unlock the saved passwords either (no Touch ID out of nowhere):
    Outlook is read in the background only once the passwords were unlocked for something else.

Only what's needed is kept: the messages live in memory; on disk she keeps a short list of
hashed message ids (so a restart doesn't announce old mail as new).
"""
import hashlib
import threading
import time

import mailread
from core import IS_WIN, load_memory, log, save_config, save_memory

from . import Feature

L = {
    "en": {"check": "Check Mail Now", "show": "Show Mail", "settings": "Mail Settings…",
           "count": lambda n: "%d important" % n if n else "Nothing important", "checking": "Looking at your mail…",
           "off": "Open Mail once to start"},
    "zh": {"check": "立即查看邮件", "show": "显示邮件", "settings": "邮件设置…",
           "count": lambda n: "%d 封重要邮件" % n if n else "没有重要邮件", "checking": "正在看邮件…",
           "off": "先打开一次邮件功能"},
}
EVERY = [15, 30, 60, 120]
HOURS = [12, 24, 48, 72]
WAKE_DELAY = 60
KEEP_SEEN = 800


def _h(mid):
    return hashlib.sha1(mid.encode()).hexdigest()[:16]


class Mail(Feature):
    id = "mail"
    icon = "✉️"
    name = "Mail"
    name_zh = "邮件"

    def __init__(self, app):
        super().__init__(app)
        self._lock = threading.Lock()
        self.busy = None              # None | "apple" | "outlook"
        self.items = []
        self.last = 0.0
        self.next_due = 0.0
        self.apple = {"st": "idle"}   # idle | ok | not_running | denied | error | off
        self.ms = {"st": "off"}       # off | ok | need | waiting | signing | error
        self._tok = None              # {"access_token", "expires_at"} in memory only
        self._sign = None             # the sign-in in progress: {"stop": bool}
        self.seen = set(load_memory(self.id).get("seen") or [])
        if self.cfg.get("ms_account"):
            self.ms = {"st": "ok", "account": self.cfg["ms_account"]}

    # ---------- settings ----------
    def _c(self, k, default):
        v = self.cfg.get(k)
        return default if v is None else v

    def every(self):
        v = int(self._c("every", 30))
        return v if v in EVERY else 30

    def hours(self):
        v = int(self._c("hours", 24))
        return v if v in HOURS else 24

    def client_id(self):
        return (self.cfg.get("ms_client_id") or "").strip()

    def tenant(self):
        t = self.cfg.get("ms_tenant") or "common"
        return t if t in ("common", "organizations", "consumers") else "common"

    # ---------- schedule ----------
    def start(self):
        if self.cfg.get("used"):
            self.next_due = time.time() + 20

    def sleep(self):
        self.next_due = 0.0

    def wake(self):
        if self.cfg.get("used"):
            self.next_due = time.time() + WAKE_DELAY

    def tick(self, now):
        if not self.cfg.get("used") or self.busy:
            return
        if not self.next_due:
            self.next_due = (self.last or now) + self.every() * 60
        if now >= self.next_due:
            self.next_due = now + self.every() * 60
            self._go(manual=False)

    def _go(self, manual):
        threading.Thread(target=self.check, args=(manual,), daemon=True).start()

    # ---------- a look at the inboxes ----------
    def check(self, manual=True):
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._check(manual)
        except Exception as e:
            log("mail: check failed %r" % e)
        finally:
            self.busy = None
            self._lock.release()
            self.app.push_soon()

    def _check(self, manual):
        c, hours = self.cfg, self.hours()
        found = []
        if c.get("apple", True):
            self.busy = "apple"
            self.app.push_soon()
            try:
                got = mailread.apple_recent(hours, 80)
                found += got
                self.apple = {"st": "ok", "n": len(got)}
            except mailread.MailError as e:
                self.apple = {"st": e.kind, "err": str(e)[:200] if e.kind == "error" else ""}
                if e.kind != "not_running":
                    log("mail: Apple Mail %s %s" % (e.kind, str(e)[:200]))
            # the old messages stay if this time Mail couldn't be read
            if self.apple["st"] != "ok":
                found += [m for m in self.items if m["src"] == "apple"]
        else:
            self.apple = {"st": "off"}
        if c.get("ms_account") and self.client_id() and self.ms.get("st") != "signing":
            self.busy = "outlook"
            self.app.push_soon()
            tok = self._token(manual)
            if tok:
                try:
                    got = mailread.ms_recent(tok, c["ms_account"], hours, 80)
                    found += got
                    self.ms = {"st": "ok", "account": c["ms_account"], "n": len(got)}
                except mailread.SignInNeeded:
                    self._tok = None
                    self.ms = {"st": "need", "account": c["ms_account"]}
                except Exception as e:
                    self.ms = {"st": "error", "account": c["ms_account"], "err": str(e)[:200]}
                    log("mail: Outlook error %s" % str(e)[:200])
            if self.ms["st"] != "ok":
                found += [m for m in self.items if m["src"] == "outlook"]
        self.items = mailread.sort_mail(found, c.get("vip", ""), c.get("mute", ""))
        self.last = time.time()
        self._news(manual)
        log("mail: %s look, %d messages (%d important), Apple %s, Outlook %s" % (
            "manual" if manual else "automatic", len(self.items), self.counts(), self.apple["st"], self.ms["st"]))

    def _news(self, manual):
        """an automatic look speaks up about new important unread mail; remember what was seen"""
        first = not self.seen
        new = [m for m in self.items if _h(m["id"]) not in self.seen]
        self.seen |= {_h(m["id"]) for m in self.items}
        if len(self.seen) > KEEP_SEEN:
            keep = {_h(m["id"]) for m in self.items}
            self.seen = keep | set(list(self.seen - keep)[:KEEP_SEEN - len(keep)])
        save_memory(self.id, {"seen": sorted(self.seen)})
        if manual or first or not self.cfg.get("notify", True):
            return
        hot = [m for m in new if m["level"] == "important" and not m["read"]]
        if hot:
            self.app.reports.add(self.id, "new", {"n": len(hot), "items": [self._row(m) for m in hot[:5]]}, live=False)

    def _token(self, manual):
        """an access token for Microsoft Graph, or None (and self.ms says why); never shows a window
        except Touch ID for the saved passwords, and that only when you asked (manual)"""
        import vault
        if self._tok and self._tok["expires_at"] > time.time():
            return self._tok["access_token"]
        acct = self.cfg["ms_account"]
        if not manual and not vault.is_unlocked():
            self.ms = {"st": "waiting", "account": acct}      # read when you open Mail
            return None
        try:
            rt = vault.get("ms:" + acct, force=manual)
        except vault.Locked:
            self.ms = {"st": "waiting", "account": acct}
            return None
        if not rt:
            self.ms = {"st": "need", "account": acct}
            return None
        try:
            t = mailread.ms_refresh(self.client_id(), rt, self.tenant())
        except mailread.SignInNeeded as e:
            log("mail: Microsoft wants a new sign-in (%s)" % str(e)[:120])
            self.ms = {"st": "need", "account": acct}
            return None
        except Exception as e:
            self.ms = {"st": "error", "account": acct, "err": str(e)[:200]}
            log("mail: Microsoft token error %s" % str(e)[:200])
            return None
        if t.get("refresh_token") and t["refresh_token"] != rt:
            vault.set("ms:" + acct, t["refresh_token"])
        self._tok = {"access_token": t["access_token"], "expires_at": t["expires_at"]}
        return self._tok["access_token"]

    # ---------- Microsoft sign-in (only when you ask) ----------
    def sign_in(self):
        if not self.client_id():
            self.ms = dict(self.ms, st="error", err="no_client")
            self.app.push_soon()
            return
        if self._sign:
            return
        job = self._sign = {"stop": False}
        prev = dict(self.ms)
        try:
            dev = mailread.ms_device_start(self.client_id(), self.tenant())
        except Exception as e:
            self._sign = None
            self.ms = dict(prev, st="error", err=str(e)[:200])
            log("mail: Microsoft sign-in couldn't start: %s" % str(e)[:200])
            self.app.push_soon()
            return
        self.ms = {"st": "signing", "account": prev.get("account", ""), "code": dev["user_code"],
                   "url": dev.get("verification_uri") or "https://microsoft.com/devicelogin",
                   "until": dev["expires_at"]}
        log("mail: Microsoft sign-in started")
        self.app.push_soon()

        def wait():
            import vault
            try:
                t = mailread.ms_device_poll(self.client_id(), dev, self.tenant(), stop=lambda: job["stop"])
                if not t:      # cancelled, or the code ran out: back to how it was
                    self.ms = dict(prev, note="" if job["stop"] else "expired")
                    return
                acct, _ = mailread.ms_me(t["access_token"])
                acct = (acct or "outlook").lower()
                old = self.cfg.get("ms_account")
                if old and old != acct:
                    vault.delete("ms:" + old)
                vault.set("ms:" + acct, t.get("refresh_token", ""))
                self.cfg["ms_account"] = acct
                save_config(self.app.cfg)
                self._tok = {"access_token": t["access_token"], "expires_at": t["expires_at"]}
                self.ms = {"st": "ok", "account": acct}
                log("mail: signed in to Microsoft")
                self._go(manual=True)
            except Exception as e:
                self.ms = dict(prev, st="error", err=str(e)[:200])
                log("mail: Microsoft sign-in failed: %s" % str(e)[:200])
            finally:
                self._sign = None
                self.app.push_soon()
        threading.Thread(target=wait, daemon=True).start()

    def cancel_sign_in(self):
        if self._sign:
            self._sign["stop"] = True

    def sign_out(self):
        import vault
        self.cancel_sign_in()
        acct = self.cfg.pop("ms_account", None)
        if acct:
            vault.delete("ms:" + acct)
        save_config(self.app.cfg)
        self._tok = None
        self.ms = {"st": "off"}
        self.items = [m for m in self.items if m["src"] != "outlook"]
        log("mail: signed out of Microsoft")
        self.app.push_soon()

    # ---------- the page ----------
    def counts(self):
        return sum(1 for m in self.items if m["level"] == "important")

    @staticmethod
    def _row(m):
        return {k: m.get(k) for k in ("id", "src", "account", "ts", "read", "from", "addr", "subject",
                                       "preview", "level", "why")}

    def state(self):
        ms = {k: v for k, v in self.ms.items()}
        return {"used": bool(self.cfg.get("used")), "busy": self.busy, "last": self.last,
                "next": self.next_due if self.cfg.get("used") else 0,
                "items": [self._row(m) for m in self.items[:80]], "important": self.counts(),
                "apple": self.apple, "ms": ms, "ms_ready": bool(self.client_id()),
                "apple_on": bool(self.cfg.get("apple", True))}

    # api.feature("mail", ...)
    def api_opened(self):
        """you opened Mail: from now on she looks in the background; a stale list is refreshed,
        and if Microsoft wants a new sign-in, now is when she shows it"""
        if not self.cfg.get("used"):
            self.cfg["used"] = True
            save_config(self.app.cfg)
        if self.ms.get("st") == "need" and self.client_id() and not self._sign:
            threading.Thread(target=self.sign_in, daemon=True).start()
        elif not self.busy and time.time() - self.last > 5 * 60:
            self._go(manual=True)
        elif self.ms.get("st") == "waiting" and not self.busy:
            self._go(manual=True)
        self.next_due = time.time() + self.every() * 60
        return True

    def api_check(self):
        if not self.cfg.get("used"):
            self.cfg["used"] = True
            save_config(self.app.cfg)
        if not self.busy:
            self._go(manual=True)
            self.next_due = time.time() + self.every() * 60
        return True

    def api_sign_in(self):
        threading.Thread(target=self.sign_in, daemon=True).start()
        return True

    def api_cancel_sign_in(self):
        self.cancel_sign_in()
        return True

    def api_sign_out(self):
        self.sign_out()
        return True

    def api_open(self, mid):
        m = next((x for x in self.items if x["id"] == mid), None)
        if not m:
            return False
        if m["src"] == "apple":
            threading.Thread(target=mailread.apple_open, args=(m["mid"],), daemon=True).start()
        elif m.get("url"):
            import webbrowser
            webbrowser.open(m["url"])
        return True

    def api_open_mail_app(self):
        try:
            mailread.open_apple_mail()
        except mailread.MailError as e:
            self.apple = {"st": "error", "err": str(e)}
            self.app.push_soon()
            return False
        threading.Timer(15 if IS_WIN else 6, lambda: self._go(manual=True)).start()     # Outlook takes its time
        return True

    def api_open_sign_in_page(self):
        url = self.ms.get("url") or "https://microsoft.com/devicelogin"
        import webbrowser
        webbrowser.open(url)
        return True

    def menu(self, lang):
        T = L.get(lang, L["en"])
        info = T["checking"] if self.busy else T["count"](self.counts()) if self.cfg.get("used") else T["off"]
        return [{"title": info, "info": True},
                {"sep": True},
                {"title": T["check"], "key": "mail:check", "enabled": not self.busy},
                {"title": T["show"], "key": "mail:show"},
                {"sep": True},
                {"title": T["settings"], "key": "mail:settings"}]

    def handle(self, action, arg=""):
        if action == "check":
            self.app.show_window()
            self.app.page_call("openFeature('mail')")
        elif action == "show":
            self.app.show_window()
            self.app.page_call("openFeature('mail')")
        elif action == "settings":
            self.app.open_settings("mail")

    def get_settings(self):
        c = self.cfg
        return {"apple": bool(c.get("apple", True)), "every": self.every(), "hours": self.hours(),
                "notify": bool(c.get("notify", True)), "vip": c.get("vip", ""), "mute": c.get("mute", ""),
                "ms_client_id": self.client_id(), "ms_tenant": self.tenant(), "ms_account": c.get("ms_account", ""),
                "everys": EVERY, "hourss": HOURS}

    def save_settings(self, s):
        c = self.cfg
        for k in ("apple", "notify"):
            if k in s:
                c[k] = bool(s[k])
        if int(s.get("every") or 0) in EVERY:
            c["every"] = int(s["every"])
        if int(s.get("hours") or 0) in HOURS:
            c["hours"] = int(s["hours"])
        for k in ("vip", "mute"):
            if k in s:
                c[k] = str(s[k] or "")[:2000]
        if "ms_client_id" in s:
            cid = str(s["ms_client_id"] or "").strip()
            if cid != self.client_id():
                self._tok = None
            c["ms_client_id"] = cid
        if s.get("ms_tenant") in ("common", "organizations", "consumers"):
            c["ms_tenant"] = s["ms_tenant"]
        # new rules: sort again right away
        self.items = mailread.sort_mail(self.items, c.get("vip", ""), c.get("mute", ""))
