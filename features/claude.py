"""Claude: she keeps an eye on Claude Code for you (macOS and Windows).

Claude Code hooks (claude_hook.py, installed from Settings → 🤖 Claude into
~/.claude/settings.json) hand her what Claude is doing over a local socket (Windows has no
such sockets in Python: there it's a port on this PC only, 127.0.0.1, and the hook has to show
a password that sits in your own data folder, claude.port):
  - Claude finished       -> a balloon: which project, and how it went (the summary Claude wrote)
  - Claude failed         -> a balloon with the error
  - Claude needs you      -> a balloon pointing you back to Claude
  - Claude asks permission (run a command, edit a file, ...) -> Allow / Always allow / Deny in her balloon
  - Claude asks a question with choices -> pick the answer in her balloon

You can always answer in Claude instead: "In Claude" (or no answer within `wait` seconds)
leaves the question to Claude's own window, exactly as without her. If the widget isn't
running, the hook does nothing.

Nothing is written to disk: the summaries live in her balloon until you confirm them; the log
only says which kind of event came in.
"""
import json
import os
import select
import shutil
import socket
import sys
import threading
import time

import plat
from core import FROZEN, HERE, HIDE, IS_WIN, log, save_config

from .chat import Chat, summary as _summary, which

import instance

SOCK = os.environ.get("PARCELWIDGET_CLAUDE_SOCK") or os.path.join(instance.BASE, "claude.sock")
PORT_FILE = os.environ.get("PARCELWIDGET_CLAUDE_PORT") or os.path.join(instance.BASE, "claude.port")   # Windows
HOOK_DST = os.path.join(instance.BASE, "claude_hook.py")
HOOK_EXE = "ParcelWidgetHook.exe"       # Windows, packaged app: the hook as a program of its own
SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
WAITS = [60, 120, 300, 600]
# Claude小姐's runs: which model, how hard it thinks, how much it can keep in mind
MODELS = ["default", "fable", "opus", "sonnet", "haiku"]
EFFORTS = ["default", "low", "medium", "high", "xhigh", "max"]
CONTEXTS = ["default", "1m"]
NO_1M = ("default", "haiku")       # 1M context needs a chosen model that has it
CHOICE_WAIT = 120     # Claude's turn stays open this long for a pick from its end-of-turn buttons
WRAP = "mcp__ccd_turn__wrap_up"         # the Claude desktop app's end-of-turn summary

L = {
    "en": {"settings": "Claude Settings…", "on": "Watching Claude Code", "off": "Not watching Claude Code",
           "ask": "Ask Claude…"},
    "zh": {"settings": "Claude 设置…", "on": "正在关注 Claude Code", "off": "没有关注 Claude Code",
           "ask": "跟 Claude 说…"},
}


def _hook_src():
    return os.path.join(HERE, "claude_hook.py")


def hook_command():
    if not IS_WIN:
        return '/usr/bin/python3 "%s"' % HOOK_DST
    # forward slashes: Claude Code runs hooks through Git Bash or PowerShell, both take them
    if FROZEN:      # no Python on the PC for sure: the hook program next to the widget's
        return '"%s"' % os.path.join(os.path.dirname(sys.executable), HOOK_EXE).replace("\\", "/")
    py = sys.executable
    if os.path.basename(py).lower() == "pythonw.exe" and os.path.exists(py[:-5] + ".exe"):
        py = py[:-5] + ".exe"           # python.exe: the one that talks through pipes for sure
    return '"%s" "%s"' % (py.replace("\\", "/"), HOOK_DST.replace("\\", "/"))


def _ours(h):
    c = str((h or {}).get("command", ""))
    return ("claude_hook.py" in c and "ParcelWidget" in c) or HOOK_EXE in c


def _hooks_wanted():
    cmd = hook_command()
    bg = {"type": "command", "command": cmd, "async": True}
    wait = {"type": "command", "command": cmd, "timeout": max(WAITS) + 30}
    return {
        "Stop": [{"hooks": [dict(wait)]}],          # waits only when Claude ended with buttons
        "StopFailure": [{"hooks": [dict(bg)]}],
        "Notification": [{"hooks": [dict(bg)]}],
        "PostToolUse": [{"matcher": "*", "hooks": [dict(bg)]}],
        "PermissionRequest": [{"matcher": "*", "hooks": [dict(wait)]}],
        "PreToolUse": [{"matcher": "AskUserQuestion", "hooks": [dict(wait)]}],
    }


def _read_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}


def _write_settings(d):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    if os.path.exists(SETTINGS) and not os.path.exists(SETTINGS + ".parcelwidget-backup"):
        shutil.copy2(SETTINGS, SETTINGS + ".parcelwidget-backup")     # the first time only
    tmp = SETTINGS + ".parcelwidget-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def _strip(hooks):
    """settings' hooks without ours (other hooks are kept as they are)"""
    out = {}
    for ev, groups in (hooks or {}).items():
        keep = []
        for g in groups if isinstance(groups, list) else []:
            hs = [h for h in (g.get("hooks") or []) if not _ours(h)]
            if hs:
                keep.append(dict(g, hooks=hs))
            elif not g.get("hooks"):
                keep.append(g)
        if keep:
            out[ev] = keep
    return out


def installed():
    hooks = _read_settings().get("hooks") or {}
    return any(_ours(h) for groups in hooks.values() if isinstance(groups, list)
               for g in groups for h in (g.get("hooks") or []))


def install():
    """copy the hook next to the widget's data and add it to Claude Code's user settings"""
    os.makedirs(instance.BASE, exist_ok=True)
    shutil.copyfile(_hook_src(), HOOK_DST)
    d = _read_settings()
    before = json.dumps(d, sort_keys=True)
    hooks = _strip(d.get("hooks"))
    for ev, groups in _hooks_wanted().items():
        hooks.setdefault(ev, []).extend(groups)
    d["hooks"] = hooks
    if json.dumps(d, sort_keys=True) != before:      # only touch the file when something changed
        _write_settings(d)


def uninstall():
    d = _read_settings()
    if "hooks" not in d:
        return
    hooks = _strip(d.get("hooks"))
    if hooks:
        d["hooks"] = hooks
    else:
        d.pop("hooks")
    _write_settings(d)


def _reset_at(text):
    """'Nov 12 at 1:09am (America/New_York)' -> epoch seconds (None if it reads differently)"""
    import datetime
    import re
    m = re.match(r"\s*([A-Za-z]{3}) (\d{1,2})(?: at (\d{1,2})(?::(\d{2}))? ?([ap]m))?\s*(?:\(([^)]+)\))?", text or "")
    if not m:
        return None
    mon, day, hh, mm, ap, tz = m.groups()
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(tz) if tz else None
        now = datetime.datetime.now(zone)
        h = (int(hh) % 12 + (12 if ap == "pm" else 0)) if hh else 0
        d = datetime.datetime.strptime("%s %s %d" % (mon, day, now.year), "%b %d %Y").replace(
            hour=h, minute=int(mm or 0), tzinfo=zone)
        if d < now - datetime.timedelta(days=180):       # December -> January
            d = d.replace(year=now.year + 1)
        return d.timestamp()
    except Exception:
        return None


def parse_usage(text):
    """the limits lines of `claude /usage`:
        Current session: 70% used · resets Nov 12 at 1:09am (America/New_York)
        Current week (all models): 19% used · resets Nov 13 at 6:59am (America/New_York)
        Current week (Fable): 9% used · ..."""
    import re
    out, more = {}, []
    for ln in (text or "").splitlines():
        m = re.match(r"\s*Current (session|week)(?: \(([^)]*)\))?\s*:\s*(\d+(?:\.\d+)?)% used(?:\s*·\s*resets (.+))?", ln)
        if not m:
            continue
        kind, which, pct, rs = m.groups()
        w = {"pct": float(pct), "resets": _reset_at(rs), "resets_text": re.sub(r"\s*\([^)]*\)\s*$", "", rs or "")}
        if kind == "session":
            out["five"] = w
        elif not which or which == "all models":
            out["week"] = w
        else:
            more.append(dict(w, name=which))
    if more:
        out["more"] = more[:3]
    return out


class Claude(Chat):
    id = "claude"
    icon = "🤖"                 # the hover button draws an orange starburst instead (ui/index.html FICONS)
    name = "Miss Claude"
    name_zh = "Claude小姐"
    hover = True

    def __init__(self, app):
        super().__init__(app)
        self._srv = None
        self._token = None            # Windows: what the hook has to show (see _listen_tcp)
        self._wrap = {}               # session -> {"recap", "ask"} from the desktop app's wrap-up
        self._pending = {}            # report id -> {"sid", "tool", "call", "answer", "conn"}
        self._plock = threading.Lock()
        self.listening = False
        self.usage = None             # your 5-hour and weekly limits, from `claude /usage`
        self._usage_ts = 0
        self._usage_busy = False

    def _c(self, k, default):
        v = self.cfg.get(k)
        return default if v is None else v

    def wait(self):
        v = int(self._c("wait", 300))
        return v if v in WAITS else 300

    # ---------- start / stop ----------
    def start(self):
        if self.cfg.get("enabled"):
            if installed():
                try:
                    install()          # keep the hook and its entries up to date (after an update)
                except Exception as e:
                    log("claude: couldn't refresh the hooks: %r" % e)
            self._listen()

    def _listen(self):
        if self._srv:
            return
        if IS_WIN:
            return self._listen_tcp()
        if os.path.exists(SOCK):
            try:
                c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                c.settimeout(1)
                c.connect(SOCK)
                c.close()
                log("claude: another copy is already listening")
                return
            except OSError:
                try:
                    os.unlink(SOCK)
                except OSError:
                    pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o077)               # only you can connect
        try:
            srv.bind(SOCK)
        finally:
            os.umask(old)
        srv.listen(16)
        self._srv = srv
        self.listening = True
        threading.Thread(target=self._accept, args=(srv,), daemon=True).start()
        log("claude: listening for Claude Code")

    def _listen_tcp(self):
        """Windows: a port on this PC only; claude.port tells the hook which, and the password"""
        import secrets
        try:
            with open(PORT_FILE, encoding="utf-8") as f:
                port = int(json.load(f)["port"])
            c = socket.create_connection(("127.0.0.1", port), timeout=1)
            c.close()
            log("claude: another copy is already listening")
            return
        except (OSError, ValueError, KeyError, TypeError):
            pass
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(16)
        self._token = secrets.token_hex(16)
        tmp = PORT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"port": srv.getsockname()[1], "token": self._token}, f)
        os.replace(tmp, PORT_FILE)
        self._srv = srv
        self.listening = True
        threading.Thread(target=self._accept, args=(srv,), daemon=True).start()
        log("claude: listening for Claude Code")

    def stop(self):
        self._stop()             # turned off: stop listening (the hooks then do nothing)

    def _stop(self):
        srv, self._srv = self._srv, None
        self.listening = False
        if srv:
            try:
                srv.close()
            except OSError:
                pass
            try:
                os.unlink(PORT_FILE if IS_WIN else SOCK)
            except OSError:
                pass

    def _accept(self, srv):
        while self._srv is srv and not self.app.closing:
            try:
                conn, _ = srv.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    # ---------- one event from the hook ----------
    def _handle(self, conn):
        keep = False
        try:
            conn.settimeout(5)
            buf = b""
            while not buf.endswith(b"\n") and len(buf) < 2_000_000:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            ev = json.loads(buf.decode("utf-8") or "{}")
            if IS_WIN:      # any program on this PC can reach the port: only the hook knows the password
                import hmac
                if not hmac.compare_digest(str(ev.pop("token", "")), self._token or "-"):
                    return
            keep = self.on_event(ev, conn)
        except Exception as e:
            log("claude: bad event %r" % e)
        finally:
            if not keep:
                try:
                    conn.close()
                except OSError:
                    pass

    def on_event(self, ev, conn=None):
        """True if the connection was kept (waiting for your answer)"""
        name = ev.get("hook_event_name") or ""
        sid = ev.get("session_id") or ""
        project = plat.base_name(ev.get("cwd") or "") or "Claude"
        rep = self.app.reports
        cwd = ev.get("cwd") or ""
        if cwd and cwd not in self._seen_cwds and not ev.get("run"):
            self._seen_cwds = ([cwd] + self._seen_cwds)[:6]
        if name in ("Stop", "StopFailure"):
            self.usage_refresh(60)       # a turn used some of your limits
        if ev.get("run") and name in ("Stop", "StopFailure", "Notification"):
            return False                 # her own runs: the chat in her balloon shows how it went
        if name == "PostToolUse":
            if ev.get("tool_name") == WRAP:
                ti = ev.get("tool_input") or {}
                acts = [a.get("label") or a.get("action") for a in (ti.get("actions") or []) if isinstance(a, dict)]
                self._wrap[sid] = {"recap": ti.get("recap") or "", "ask": ti.get("ask") or "",
                                   "actions": [a for a in acts if a][:3], "app": [a.get("action") or "" for a in
                                                                              (ti.get("actions") or []) if isinstance(a, dict)][:3]}
            self._answered_elsewhere(sid, ev.get("tool_name"), ev.get("call"))
            return False
        log("claude: %s%s" % (name, (" " + ev.get("notification_type")) if ev.get("notification_type") else ""))
        if name == "Stop":
            self._answered_elsewhere(sid)
            w = self._wrap.pop(sid, None)
            if w is None and conn:
                for _ in range(8):             # the wrap-up note (async) may land a moment later
                    time.sleep(0.1)
                    if sid in self._wrap:
                        w = self._wrap.pop(sid)
                        break
            w = w or {}
            if not self._c("done", True):
                return False
            for r in list(rep.items):         # one "finished" balloon per session: the newest
                if r["feature"] == self.id and r["kind"] == "done" and r["data"].get("sid") == sid:
                    rep.drop(r)
            data = {"sid": sid, "project": project, "ask": w.get("ask", ""),
                    "summary": _summary(w.get("recap") or ev.get("last_assistant_message"))}
            if conn and w.get("ask") and w.get("actions") and self._c("questions", True):
                data.update(actions=w["actions"], app=w.get("app") or [])
                return self._ask(conn, "done", data, ev, wait=CHOICE_WAIT)
            rep.add(self.id, "done", data, live=False)
            self._attention()
            return False
        if name == "StopFailure":
            self._answered_elsewhere(sid)
            rep.add(self.id, "failed", {"sid": sid, "project": project, "error": _summary(str(ev.get("error") or ""), 300)},
                    live=False)
            self._attention()
            return False
        if name == "Notification":
            kind = ev.get("notification_type") or ""
            if kind in ("permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input"):
                with self._plock:
                    if any(p["sid"] == sid for p in self._pending.values()):
                        return False          # already asking in her balloon
                if self._c("done", True):
                    rep.add(self.id, "needs", {"sid": sid, "project": project, "message": _summary(ev.get("message"), 300)},
                            live=False)
                    self._attention()
            return False
        if name == "PermissionRequest" and conn and self._c("permissions", True):
            data = {"sid": sid, "project": project, "tool": ev.get("tool_name") or "",
                    "input": ev.get("tool_input") or {}, "always": bool(ev.get("permission_suggestions")),
                    "run": bool(ev.get("run"))}      # from a task you typed in her chat: shown big (battle mode)
            return self._ask(conn, "permission", data, ev)
        if name == "PreToolUse" and ev.get("tool_name") == "AskUserQuestion" and conn and self._c("questions", True):
            qs = (ev.get("tool_input") or {}).get("questions") or []
            if qs:
                return self._ask(conn, "question", {"sid": sid, "project": project, "questions": qs,
                                                    "run": bool(ev.get("run"))}, ev)
        return False

    def _attention(self):
        try:
            self.app.show_window()
        except Exception:
            pass

    # ---------- questions that wait for you ----------
    def _ask(self, conn, kind, data, ev, wait=None):
        data["until"] = time.time() + (wait or self.wait())
        r = self.app.reports.add(self.id, kind, data, live=False)
        p = {"sid": data["sid"], "tool": ev.get("tool_name"), "call": ev.get("call"), "answer": None, "done": False}
        with self._plock:
            self._pending[r["id"]] = p
        self._attention()
        threading.Thread(target=self._wait, args=(conn, r, p), daemon=True).start()
        return True

    def _wait(self, conn, r, p):
        ans, why = None, "timeout"
        end = r["data"]["until"]
        try:
            while time.time() < end and not self.app.closing:
                if p["answer"] is not None:
                    ans, why = p["answer"], "answered"
                    break
                if p["done"] or r not in self.app.reports.items:
                    why = "elsewhere"           # confirmed away ("In Claude"), or Claude went on
                    break
                ready, _, _ = select.select([conn], [], [], 0.3)
                if ready:
                    try:
                        if not conn.recv(1, socket.MSG_PEEK):
                            why = "hook gone"   # Claude stopped waiting for the hook
                            break
                    except OSError:
                        why = "hook gone"
                        break
            try:
                conn.sendall((json.dumps(ans if ans is not None else {"skip": True}) + "\n").encode())
            except OSError:
                pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            with self._plock:
                self._pending.pop(r["id"], None)
            gone = r not in self.app.reports.items
            self.app.reports.drop(r)
            if r["kind"] == "done" and why in ("timeout", "hook gone") and not gone:
                # not picked here: keep the summary, without the buttons
                d = {k: v for k, v in r["data"].items() if k not in ("actions", "app", "until")}
                self.app.reports.add(self.id, "done", d, live=False)
            log("claude: %s %s" % (r["kind"], why))

    def _answered_elsewhere(self, sid, tool=None, call=None):
        """the tool ran / the turn ended: questions about it were answered in Claude"""
        with self._plock:
            for p in self._pending.values():
                if p["sid"] == sid and (tool is None or (p["tool"] == tool and (not call or p["call"] == call))):
                    p["done"] = True

    # api.feature("claude", "answer", report_id, answer)
    def api_answer(self, rid, ans):
        with self._plock:
            p = self._pending.get(int(rid))
        if not p or not isinstance(ans, dict):
            return False
        if ans.get("behavior") in ("allow", "deny"):
            p["answer"] = {"behavior": ans["behavior"], "always": bool(ans.get("always"))}
        elif ans.get("choice"):
            r = next((x for x in self.app.reports.items if x["id"] == int(rid)), None)
            acts = (r or {}).get("data", {}).get("actions") or []
            if ans["choice"] not in acts:
                return False
            p["answer"] = {"choice": ans["choice"], "ask": r["data"].get("ask", "")}
        elif isinstance(ans.get("answers"), dict):
            p["answer"] = {"answers": {str(k): str(v) for k, v in ans["answers"].items()}}
        else:
            p["answer"] = {"skip": True}
        return True

    def api_open_claude(self):
        import subprocess
        try:
            if IS_WIN:
                plat.open_path("claude://")        # the desktop app registers this address
            else:
                subprocess.Popen(["open", "-a", "Claude"])
        except OSError:
            return False
        return True


    # ---------- Claude小姐: type a task in her balloon (the chat itself is in features/chat.py) ----------
    def _bin(self):
        return which("claude")

    def _stdin(self, turn):
        return turn["q"] if IS_WIN else None        # see Chat._stdin

    def _cmd(self, b, turn, cwd):
        cmd = [b, "-p"] + ([] if IS_WIN else [turn["q"]]) + ["--output-format", "stream-json", "--verbose"]
        o = self.run_opts()
        if o["model"] != "default":
            cmd += ["--model", o["model"] + ("[1m]" if o["context"] == "1m" else "")]
        if o["effort"] != "default":
            cmd += ["--effort", o["effort"]]
        if self.chat.get("sid"):
            cmd += ["--resume", self.chat["sid"]]
        return cmd

    def _env(self, b):
        return dict(super()._env(b), PARCELWIDGET_RUN="1")     # the hook marks these runs as hers

    def _on_stream(self, m, turn):
        t = m.get("type")
        if m.get("session_id"):
            self.chat["sid"] = m["session_id"]
        if t == "assistant":
            for c in (m.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    i = c.get("input") or {}
                    what = i.get("description") or i.get("command") or i.get("file_path") or i.get("pattern") \
                        or i.get("url") or i.get("query") or ""
                    turn["step"] = ("%s: %s" % (c.get("name"), what))[:160] if what else c.get("name", "")
                elif c.get("type") == "text" and c.get("text", "").strip():
                    turn["step"] = c["text"].strip().splitlines()[0][:160]
        elif t == "result":
            turn["a"] = m.get("result") or ""
            turn["st"] = "error" if m.get("is_error") else "done"

    # ---------- your plan's limits (the battery in her balloon) ----------
    def api_opened(self):
        self.usage_refresh(30)
        return super().api_opened()

    def usage_refresh(self, min_age=60):
        """ask `claude -p /usage` again (a local command: no tokens) unless it's fresher than min_age s"""
        b = self._bin()
        if not b or self._usage_busy or time.time() - self._usage_ts < min_age:
            return
        self._usage_busy = True
        threading.Thread(target=self._usage_fetch, args=(b,), daemon=True).start()

    def _usage_fetch(self, b):
        import subprocess
        try:
            r = subprocess.run([b, "-p", "/usage", "--output-format", "json", "--no-session-persistence"],
                               cwd=os.path.expanduser("~"), env=self._env(b), stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, **HIDE)
            u = parse_usage((json.loads(r.stdout or "{}") or {}).get("result") or "")
            if u:
                self.usage = dict(u, ts=time.time())
                self.app.push_soon()
            else:
                log("claude: /usage said nothing about limits")
        except Exception as e:
            log("claude: /usage failed %r" % type(e).__name__)
        finally:
            self._usage_ts = time.time()
            self._usage_busy = False

    def run_opts(self):
        o = {"model": self.cfg.get("model"), "effort": self.cfg.get("effort"), "context": self.cfg.get("context")}
        o["model"] = o["model"] if o["model"] in MODELS else "default"
        o["effort"] = o["effort"] if o["effort"] in EFFORTS else "default"
        o["context"] = o["context"] if o["context"] in CONTEXTS and o["model"] not in NO_1M else "default"
        return o

    def set_opts(self, s):
        for k, ok in (("model", MODELS), ("effort", EFFORTS), ("context", CONTEXTS)):
            if s.get(k) in ok:
                self.cfg[k] = s[k]

    def api_set_opt(self, key, value):
        """the pickers in her balloon (takes effect from the next message)"""
        self.set_opts({key: value})
        save_config(self.app.cfg)
        return self.run_opts()

    def state(self):
        if self.viewing:
            self.usage_refresh(300)
        return dict(self.chat_state(), listening=self.listening, usage=self.usage, opts=self.run_opts(),
                    choices={"model": MODELS, "effort": EFFORTS, "context": CONTEXTS, "no_1m": list(NO_1M)})

    # ---------- settings ----------
    def menu(self, lang):
        T = L.get(lang, L["en"])
        return [{"title": T["on"] if self.listening else T["off"], "info": True},
                {"sep": True},
                {"title": T["ask"], "key": "claude:show"},
                {"title": T["settings"], "key": "claude:settings"}]

    def handle(self, action, arg=""):
        if action == "settings":
            self.app.open_settings("claude")
        elif action == "show":
            self.app.show_window()
            self.app.page_call("openFeature('claude')")

    def get_settings(self):
        return {"enabled": bool(self.cfg.get("enabled")), "installed": installed(), "listening": self.listening,
                "done": bool(self._c("done", True)), "permissions": bool(self._c("permissions", True)),
                "questions": bool(self._c("questions", True)), "wait": self.wait(), "waits": WAITS,
                "opts": self.run_opts(), "models": MODELS, "efforts": EFFORTS, "contexts": CONTEXTS, "no_1m": list(NO_1M),
                "settings_path": plat.home_short(SETTINGS)}

    def save_settings(self, s):
        c = self.cfg
        for k in ("done", "permissions", "questions"):
            if k in s:
                c[k] = bool(s[k])
        self.set_opts(s)
        if int(s.get("wait") or 0) in WAITS:
            c["wait"] = int(s["wait"])
        if "enabled" in s and bool(s["enabled"]) != bool(c.get("enabled")):
            if s["enabled"]:
                install()
                c["enabled"] = True
                self._listen()
                log("claude: hooks added to %s" % SETTINGS)
            else:
                uninstall()
                c["enabled"] = False
                self._stop()
                log("claude: hooks removed from %s" % SETTINGS)
            save_config(self.app.cfg)
