"""Codex: type a task in her balloon, run by OpenAI's Codex command line (macOS and Windows).

Like Claude小姐 (features/claude.py), with `codex exec`: one non-interactive run in the folder
you picked, signed in as you (the ChatGPT account Codex already uses, its model and settings
from ~/.codex/config.toml). Follow-ups resume the same Codex conversation.

Codex can't ask for permission in a run like this, so it works inside its own sandbox:
    workspace-write   reads anything, writes only in the chosen folder, no network (the default)
    read-only         looks and answers, changes nothing
(config.json: "codex": {"sandbox": "read-only"})
"""
import glob
import json
import os
import re
import time

from core import IS_MAC, IS_WIN, save_config

from .chat import Chat, which

CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")

# the ChatGPT / Codex desktop apps carry the command line inside them (macOS; on Windows it's
# found on the PATH or in npm's folder: npm install -g @openai/codex)
APP_BINS = ["/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
            "/Applications/Codex.app/Contents/Resources/codex-cli/bin/codex",
            "/Applications/Codex.app/Contents/Resources/codex"] if IS_MAC else []
# how Codex wraps the commands it runs, taken off before showing them
SHELLS = re.compile(r'^(?:/bin/zsh -lc |/bin/bash -lc |zsh -lc |bash -lc |'
                    r'"?(?:[A-Za-z]:[^"]*[\\/])?(?:pwsh|powershell)(?:\.exe)?"? (?:-NoProfile )?-Command )', re.I)
SANDBOXES = ("workspace-write", "read-only")

L = {
    "en": {"ask": "Ask Codex…", "none": "Codex isn't installed"},
    "zh": {"ask": "跟 Codex 说…", "none": "没有安装 Codex"},
}


EFFORT_ORDER = ["minimal", "low", "medium", "high", "xhigh", "max", "ultra"]


def _find(v, key):
    """the first `key` anywhere in a JSON value"""
    if isinstance(v, dict):
        if key in v:
            return v[key]
        v = list(v.values())
    if isinstance(v, list):
        for x in v:
            r = _find(x, key)
            if r is not None:
                return r
    return None


class Codex(Chat):
    id = "codex"
    icon = "🌀"                 # the hover button draws a prompt sign instead (ui/index.html FICONS)
    name = "Codex"
    name_zh = "Codex"
    hover = True

    def __init__(self, app):
        super().__init__(app)
        self._usage_key, self._usage = None, None

    def _bin(self):
        return which("codex", APP_BINS)

    # ---------- which model, how hard it thinks (Codex's own list of models) ----------
    def models(self):
        """[{slug, name, efforts, context}] from Codex's model list (~/.codex/models_cache.json)"""
        try:
            with open(os.path.join(CODEX_HOME, "models_cache.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return []
        out = []
        for m in (d.get("models") if isinstance(d, dict) else d) or []:
            if isinstance(m, dict) and m.get("slug") and m.get("visibility", "list") == "list":
                name = m.get("display_name") or m["slug"]
                out.append({"slug": m["slug"], "name": re.sub(r"^gpt[-\s]*", "", name, flags=re.I) or name,   # "6.1-Sol"
                            "efforts": [e.get("effort") for e in m.get("supported_reasoning_levels") or []
                                        if isinstance(e, dict) and e.get("effort")],
                            "context": m.get("context_window")})
        return out[:12]

    def run_opts(self):
        ms = {m["slug"]: m for m in self.models()}
        model = self.cfg.get("model") if self.cfg.get("model") in ms else "default"
        ok = ms[model]["efforts"] if model != "default" else sorted({e for m in ms.values() for e in m["efforts"]})
        effort = self.cfg.get("effort") if self.cfg.get("effort") in ok else "default"
        return {"model": model, "effort": effort}

    def set_opts(self, s):
        if "model" in s and isinstance(s["model"], str):
            self.cfg["model"] = s["model"]
        if "effort" in s and isinstance(s["effort"], str):
            self.cfg["effort"] = s["effort"]
        o = self.run_opts()                 # anything it doesn't know goes back to the default
        self.cfg["model"], self.cfg["effort"] = o["model"], o["effort"]

    def api_set_opt(self, key, value):
        if key in ("model", "effort"):
            self.set_opts({key: value})
            save_config(self.app.cfg)
        return self.run_opts()

    def choices(self):
        ms = self.models()
        o = self.run_opts()
        cur = next((m for m in ms if m["slug"] == o["model"]), None)
        efforts = cur["efforts"] if cur else sorted({e for m in ms for e in m["efforts"]},
                                                     key=lambda e: EFFORT_ORDER.index(e) if e in EFFORT_ORDER else 99)
        return {"model": ["default"] + [m["slug"] for m in ms], "effort": ["default"] + efforts,
                "labels": {"model": {m["slug"]: m["name"] for m in ms}},
                "ctx": cur["context"] if cur else None}

    # ---------- your plan's limits, as Codex last saw them (its session logs) ----------
    def usage(self):
        """the newest rate_limits Codex wrote: 5-hour (primary) and weekly (secondary) windows"""
        files = []
        for day in sorted(glob.glob(os.path.join(CODEX_HOME, "sessions", "*", "*", "*")), reverse=True)[:3]:
            files += glob.glob(os.path.join(day, "*.jsonl"))
        try:
            files.sort(key=os.path.getmtime, reverse=True)
        except OSError:
            return None
        for f in files[:5]:
            try:
                key = (f, os.path.getmtime(f))
                if self._usage_key == key:
                    return self._usage
                with open(f, "rb") as fh:
                    fh.seek(0, 2)
                    fh.seek(max(0, fh.tell() - 400000))
                    lines = fh.read().decode("utf-8", "replace").splitlines()
            except OSError:
                continue
            for ln in reversed(lines):
                if '"rate_limits"' not in ln:
                    continue
                try:
                    rl = _find(json.loads(ln), "rate_limits")
                except ValueError:
                    continue
                if isinstance(rl, dict):
                    u = {}
                    for k, name in (("primary", "five"), ("secondary", "week")):
                        w = rl.get(k)
                        if isinstance(w, dict) and w.get("used_percent") is not None:
                            gone = w.get("resets_at") and w["resets_at"] < time.time()
                            u[name] = {"pct": 0.0 if gone else float(w["used_percent"]), "resets": None if gone else w.get("resets_at"),
                                       "mins": w.get("window_minutes")}
                    if u:
                        self._usage_key, self._usage = key, dict(u, ts=os.path.getmtime(f))
                        return self._usage
        return None

    def sandbox(self):
        s = self.cfg.get("sandbox")
        return s if s in SANDBOXES else SANDBOXES[0]

    def _stdin(self, turn):
        return turn["q"] if IS_WIN else None

    def _cmd(self, b, turn, cwd):
        # options before "--": what you typed is never read as an option
        # (Windows: no quotes inside the arguments, they don't survive a .cmd script; Codex takes a
        # bare word as text all the same. What you typed goes in on standard input: "-")
        val = "%s" if IS_WIN else '"%s"'
        opts = ["--json", "--skip-git-repo-check", "-c", "sandbox_mode=" + val % self.sandbox()]
        o = self.run_opts()
        if o["model"] != "default":
            opts += ["-m", o["model"]]
        if o["effort"] != "default":
            opts += ["-c", "model_reasoning_effort=" + val % o["effort"]]
        q = "-" if IS_WIN else turn["q"]
        if self.chat.get("sid"):
            return [b, "exec", "resume"] + opts + ["--", self.chat["sid"], q]
        return [b, "exec"] + opts + ["--", q]

    def _on_stream(self, m, turn):
        t = m.get("type")
        if t == "thread.started" and m.get("thread_id"):
            self.chat["sid"] = m["thread_id"]
        elif t in ("item.started", "item.updated", "item.completed"):
            it = m.get("item") or {}
            kind = it.get("type")
            if kind == "agent_message":
                if t == "item.completed" and (it.get("text") or "").strip():
                    turn["a"] = it["text"].strip()            # the last one is the answer
                    turn["step"] = turn["a"].splitlines()[0][:160]
            elif kind == "command_execution":
                cmd = it.get("command") or ""
                m = SHELLS.match(cmd)
                if m:
                    cmd = cmd[m.end():].strip("'\"")
                turn["step"] = ("$ " + cmd)[:160]
            elif kind == "file_change":
                paths = [(c.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1] for c in it.get("changes") or []
                         if isinstance(c, dict)]
                turn["step"] = ("✎ " + ", ".join(p for p in paths if p))[:160]
            elif kind == "mcp_tool_call":
                turn["step"] = ("%s › %s" % (it.get("server") or "", it.get("tool") or ""))[:160]
            elif kind == "web_search":
                turn["step"] = ("🔎 " + (it.get("query") or ""))[:160]
        elif t == "turn.completed":
            turn["st"] = "done"
        elif t == "turn.failed":
            turn["st"], turn["a"] = "error", str((m.get("error") or {}).get("message") or "failed")[:600]
        elif t == "error" and m.get("message"):
            turn["a"] = str(m["message"])[:600]               # shown if the run ends here (a retry replaces it)

    def state(self):
        return dict(self.chat_state(), opts=self.run_opts(), choices=self.choices(), usage=self.usage())

    def menu(self, lang):
        T = L.get(lang, L["en"])
        if not self._bin():
            return [{"title": T["none"], "info": True}]
        return [{"title": T["ask"], "key": "codex:show"}]

    def handle(self, action, arg=""):
        self.app.show_window()
        self.app.page_call("openFeature('codex')")

    def get_settings(self):
        return {"sandbox": self.sandbox(), "opts": self.run_opts(), "choices": self.choices()}

    def save_settings(self, s):
        self.set_opts({k: s[k] for k in ("model", "effort") if k in s})
        if s.get("sandbox") in SANDBOXES:
            self.cfg["sandbox"] = s["sandbox"]
