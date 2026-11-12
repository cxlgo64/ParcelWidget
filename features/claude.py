"""Claude: she keeps an eye on Claude Code for you (macOS).

Claude Code hooks (claude_hook.py, installed from Settings → 🤖 Claude into
~/.claude/settings.json) hand her what Claude is doing over a local socket:
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
import threading
import time

from core import HERE, log, save_config

from . import Feature

import instance

SOCK = os.environ.get("PARCELWIDGET_CLAUDE_SOCK") or os.path.join(instance.BASE, "claude.sock")
HOOK_DST = os.path.join(instance.BASE, "claude_hook.py")
SETTINGS = os.path.expanduser("~/.claude/settings.json")
WAITS = [60, 120, 300, 600]
WRAP = "mcp__ccd_turn__wrap_up"         # the Claude desktop app's end-of-turn summary

L = {
    "en": {"settings": "Claude Settings…", "on": "Watching Claude Code", "off": "Not watching Claude Code"},
    "zh": {"settings": "Claude 设置…", "on": "正在关注 Claude Code", "off": "没有关注 Claude Code"},
}


def _hook_src():
    return os.path.join(HERE, "claude_hook.py")


def hook_command():
    return '/usr/bin/python3 "%s"' % HOOK_DST


def _ours(h):
    return "claude_hook.py" in str((h or {}).get("command", "")) and "ParcelWidget" in str(h.get("command", ""))


def _hooks_wanted():
    cmd = hook_command()
    bg = {"type": "command", "command": cmd, "async": True}
    wait = {"type": "command", "command": cmd, "timeout": max(WAITS) + 30}
    return {
        "Stop": [{"hooks": [dict(bg)]}],
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
    hooks = _strip(d.get("hooks"))
    for ev, groups in _hooks_wanted().items():
        hooks.setdefault(ev, []).extend(groups)
    d["hooks"] = hooks
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


def _summary(text, n=600):
    t = (text or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


class Claude(Feature):
    id = "claude"
    icon = "🤖"
    name = "Claude"
    name_zh = "Claude"
    hover = False

    def __init__(self, app):
        super().__init__(app)
        self._srv = None
        self._wrap = {}               # session -> {"recap", "ask"} from the desktop app's wrap-up
        self._pending = {}            # report id -> {"sid", "tool", "call", "answer", "conn"}
        self._plock = threading.Lock()
        self.listening = False

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
                    shutil.copyfile(_hook_src(), HOOK_DST)       # keep the hook up to date
                except OSError:
                    pass
            self._listen()

    def _listen(self):
        if self._srv:
            return
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

    def _stop(self):
        srv, self._srv = self._srv, None
        self.listening = False
        if srv:
            try:
                srv.close()
            except OSError:
                pass
            try:
                os.unlink(SOCK)
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
        project = os.path.basename((ev.get("cwd") or "").rstrip("/")) or "Claude"
        rep = self.app.reports
        if name == "PostToolUse":
            if ev.get("tool_name") == WRAP:
                ti = ev.get("tool_input") or {}
                self._wrap[sid] = {"recap": ti.get("recap") or "", "ask": ti.get("ask") or ""}
            self._answered_elsewhere(sid, ev.get("tool_name"), ev.get("call"))
            return False
        log("claude: %s%s" % (name, (" " + ev.get("notification_type")) if ev.get("notification_type") else ""))
        if name == "Stop":
            self._answered_elsewhere(sid)
            w = self._wrap.pop(sid, {})
            if self._c("done", True):
                for r in list(rep.items):     # one "finished" balloon per session: the newest
                    if r["feature"] == self.id and r["kind"] == "done" and r["data"].get("sid") == sid:
                        rep.drop(r)
                rep.add(self.id, "done", {"sid": sid, "project": project,
                                          "summary": _summary(w.get("recap") or ev.get("last_assistant_message")),
                                          "ask": w.get("ask", "")}, live=False)
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
                    "input": ev.get("tool_input") or {}, "always": bool(ev.get("permission_suggestions"))}
            return self._ask(conn, "permission", data, ev)
        if name == "PreToolUse" and ev.get("tool_name") == "AskUserQuestion" and conn and self._c("questions", True):
            qs = (ev.get("tool_input") or {}).get("questions") or []
            if qs:
                return self._ask(conn, "question", {"sid": sid, "project": project, "questions": qs}, ev)
        return False

    def _attention(self):
        try:
            self.app.show_window()
        except Exception:
            pass

    # ---------- questions that wait for you ----------
    def _ask(self, conn, kind, data, ev):
        data["until"] = time.time() + self.wait()
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
            self.app.reports.drop(r)
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
        elif isinstance(ans.get("answers"), dict):
            p["answer"] = {"answers": {str(k): str(v) for k, v in ans["answers"].items()}}
        else:
            p["answer"] = {"skip": True}
        return True

    def api_open_claude(self):
        import subprocess
        subprocess.Popen(["open", "-a", "Claude"])
        return True

    # ---------- settings ----------
    def state(self):
        return {"listening": self.listening}

    def menu(self, lang):
        T = L.get(lang, L["en"])
        return [{"title": T["on"] if self.listening else T["off"], "info": True},
                {"sep": True},
                {"title": T["settings"], "key": "claude:settings"}]

    def handle(self, action, arg=""):
        if action == "settings":
            self.app.open_settings("claude")

    def get_settings(self):
        return {"enabled": bool(self.cfg.get("enabled")), "installed": installed(), "listening": self.listening,
                "done": bool(self._c("done", True)), "permissions": bool(self._c("permissions", True)),
                "questions": bool(self._c("questions", True)), "wait": self.wait(), "waits": WAITS,
                "settings_path": SETTINGS.replace(os.path.expanduser("~"), "~")}

    def save_settings(self, s):
        c = self.cfg
        for k in ("done", "permissions", "questions"):
            if k in s:
                c[k] = bool(s[k])
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
