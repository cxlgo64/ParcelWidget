"""A chat in her balloon, run by a coding agent's command line (Claude Code, Codex).

What you type is one non-interactive run of the command line in the folder you picked; she
shows what the agent is doing, then its answer. Follow-ups resume the same conversation.

A feature built on this says:
    _bin()                  where the command line is (None: not installed)
    _cmd(b, turn, cwd)      the command for one turn (self.chat["sid"] is the conversation to resume)
    _on_stream(m, turn)     one JSON line of its output: set turn["step"] while it works, and
                            turn["a"] + turn["st"] ("done" / "error") at the end; self.chat["sid"]
                            when it says which conversation this is
    _env(b)                 the environment of the run
"""
import json
import os
import shutil
import subprocess
import threading
import time

from core import HIDE, IS_WIN, log, save_config
from plat import base_name

from . import Feature

if IS_WIN:
    _H, _E = os.path.expanduser("~"), os.environ
    # the native installers, npm's global folder, and the usual package managers
    PATHS = [os.path.join(_H, ".local", "bin"), os.path.join(_E.get("APPDATA", _H), "npm"),
             os.path.join(_E.get("LOCALAPPDATA", _H), "Microsoft", "WinGet", "Links"),
             os.path.join(_H, "scoop", "shims"), os.path.join(_H, ".bun", "bin")]
else:
    PATHS = [os.path.expanduser("~/.local/bin"), "/opt/homebrew/bin", "/usr/local/bin"]


def which(name, more=()):
    """the command line `name`: on the PATH, in the usual places, or at one of `more`"""
    b = shutil.which(name, path=os.pathsep.join([os.environ.get("PATH", "")] + PATHS))
    return b or next((p for p in more if os.path.isfile(p) and os.access(p, os.X_OK)), None)


def summary(text, n=600):
    t = (text or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


class Chat(Feature):
    def __init__(self, app):
        super().__init__(app)
        self.chat = {"sid": None, "turns": []}
        self._proc = None
        self._stopping = False        # you pressed Stop
        self._busy = False            # set the moment you press Send (the process starts a moment later)
        self._block = threading.Lock()
        self.viewing = False
        self._seen_cwds = []          # folders the agent worked in lately (offered as places to run)

    # ---------- what a feature fills in ----------
    def _bin(self):
        return None

    def _cmd(self, b, turn, cwd):
        raise NotImplementedError

    def _on_stream(self, m, turn):
        pass

    def _stdin(self, turn):
        """text to hand the command line on its standard input (None: nothing). Windows: what you
        typed goes in this way, not as an argument - the command lines installed with npm are
        .cmd scripts, and cmd.exe would read & | < > % " in your text as commands."""
        return None

    def _env(self, b):
        extra = [os.path.dirname(b)] + ([] if IS_WIN else ["/usr/bin", "/bin"])
        return dict(os.environ, PATH=os.pathsep.join([os.environ.get("PATH", "")] + extra))

    # ---------- the folder it runs in ----------
    def folders(self):
        """where she can run it: the chosen folder first, then folders it worked in lately"""
        out = []
        for f in [self.cfg.get("folder")] + list(self.cfg.get("folders") or []) + self._seen_cwds:
            if f and os.path.isdir(f) and f not in out:
                out.append(f)
        return out[:6] or [os.path.expanduser("~")]

    def api_folder(self, path):
        if path and os.path.isdir(path):
            self.cfg["folder"] = path
            self.cfg["folders"] = ([path] + [f for f in (self.cfg.get("folders") or []) if f != path])[:6]
            save_config(self.app.cfg)
            self.chat = {"sid": None, "turns": []}       # another project: a new conversation
        return True

    def api_pick_folder(self):
        try:
            import webview
            res = self.app.window.create_file_dialog(webview.FileDialog.FOLDER)
        except Exception as e:
            log("%s: folder picker failed %r" % (self.id, e))
            return False
        if res:
            self.api_folder(res[0] if isinstance(res, (list, tuple)) else res)
        return True

    # ---------- the chat ----------
    def api_opened(self):
        self.viewing = True
        return True

    def api_closed(self):
        self.viewing = False
        return True

    def api_new_chat(self):
        if not self._busy:
            self.chat = {"sid": None, "turns": []}
        return True

    def api_stop_run(self):
        p = self._proc
        if p:
            self._stopping = True
            try:
                if IS_WIN:       # the whole tree: a .cmd script is cmd.exe, the agent is its child
                    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, timeout=15, **HIDE)
                else:
                    p.terminate()
            except (OSError, subprocess.SubprocessError):
                pass
        return True

    def api_send(self, text):
        text = (text or "").strip()
        if not text:
            return {"ok": False}
        b = self._bin()
        if not b:
            return {"ok": False, "err": "no_cli"}
        with self._block:
            if self._busy:
                return {"ok": False, "err": "busy"}
            self._busy = True
        turn = {"q": text[:4000], "a": "", "st": "running", "step": "", "ts": time.time(), "secs": 0}
        self.chat["turns"] = (self.chat["turns"] + [turn])[-12:]
        threading.Thread(target=self._run, args=(b, turn, self.folders()[0]), daemon=True).start()
        self.app.push_soon()
        return {"ok": True}

    def _run(self, b, turn, cwd):
        log("%s: run started in %s" % (self.id, base_name(cwd)))
        self._stopping = False
        try:
            feed = self._stdin(turn)
            p = self._proc = subprocess.Popen(self._cmd(b, turn, cwd), cwd=cwd, env=self._env(b),
                                              stdin=subprocess.DEVNULL if feed is None else subprocess.PIPE,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                              encoding="utf-8", errors="replace", bufsize=1, **HIDE)
            if feed is not None:
                try:
                    p.stdin.write(feed)
                    p.stdin.close()
                except OSError:
                    pass
            errs = []
            t = threading.Thread(target=lambda: errs.append(p.stderr.read()), daemon=True)
            t.start()                  # read alongside: a full stderr pipe would stall the run
            for line in p.stdout:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if isinstance(m, dict):
                    self._on_stream(m, turn)
                    self.app.push_soon()
            p.wait()
            t.join(2)
            err = ("".join(e or "" for e in errs)).strip()[-300:]
            if turn["st"] == "running":
                turn["st"] = "stopped" if self._stopping or p.returncode in (-15, 143) else "error"
                turn["a"] = turn["a"] or err or ("exit %s" % p.returncode)
        except Exception as e:
            turn["st"], turn["a"] = "error", str(e)[:300]
        finally:
            self._proc = None
            self._busy = False
            turn["secs"] = round(time.time() - turn["ts"])
            turn["step"] = ""
            log("%s: run %s after %d s" % (self.id, turn["st"], turn["secs"]))
            if not self.viewing and turn["st"] in ("done", "error"):
                self.app.reports.add(self.id, "reply", {"q": turn["q"][:300], "a": summary(turn["a"], 1500),
                                                        "st": turn["st"], "project": base_name(cwd)}, live=False)
                try:
                    self.app.show_window()
                except Exception:
                    pass
            self.app.push_soon()

    def chat_state(self):
        return {"running": self._busy, "cli": bool(self._bin()),
                "chat": {"turns": self.chat["turns"], "has_sid": bool(self.chat.get("sid"))},
                "folders": [{"path": f, "name": base_name(f) or f} for f in self.folders()]}
