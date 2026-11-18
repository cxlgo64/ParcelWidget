"""WorkBuddy: watch WorkBuddy, and start a chat in her balloon.

WorkBuddy's desktop app bundles CodeBuddy Code (a Claude Code-compatible CLI)
at resources/app.asar.unpacked/cli/bin/codebuddy. It speaks the same hook
language, so watching works exactly as features/claude.py does:
  - WorkBuddy finished / failed  -> a balloon: which folder, and how it went
  - WorkBuddy needs you          -> a balloon pointing you back to WorkBuddy
  - permission requests / questions with choices -> answer in her balloon

On top of that, this feature now has the chat Claude小姐 and Codex have:
features/chat.py lets you pick a folder, then runs one non-interactive CLI turn
in it, streams what it does and shows the answer. Follow-ups --resume the same
session; "Stop" ends the run. PARCELWIDGET_RUN=1 marks these runs as hers, so
the hook doesn't report them as somebody else's WorkBuddy task. The same hooks
are also installed into the CLI's own settings, so its permission requests and
questions come back to her balloon too.

The CLI keeps its own sign-in in ~/.codebuddy/.credentials.json (outside this
repo and gitignored). Sign in once with the full npm CLI
(`npm i -g @tencent-ai/codebuddy-code`, then CodeBuddy-Login.cmd on the Windows
Desktop shows the "Select login method" panel). The CLI bundled inside the app
is a headless lite-wb build with no login UI, so _cli_js() prefers the full
CLI and only falls back to the bundled one. Nothing here reads, copies or
stores a token.
"""
import glob
import os
import shutil
import socket
import sys

import plat
from core import log

from .claude import Claude, install, installed

import instance

IS_WIN = sys.platform == "win32"
HOME = os.environ.get("WORKBUDDY_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".workbuddy")

L = {
    "en": {"settings": "WorkBuddy Settings…", "on": "Watching WorkBuddy", "off": "Not watching WorkBuddy",
           "open": "Open WorkBuddy", "chat": "Chat with WorkBuddy…", "login": "Sign in to CodeBuddy…"},
    "zh": {"settings": "WorkBuddy 设置…", "on": "正在关注 WorkBuddy", "off": "没有关注 WorkBuddy",
           "open": "打开 WorkBuddy", "chat": "和 WorkBuddy 说…", "login": "登录 CodeBuddy…"},
}

LOGIN_HINT = ("命令行还没登录：打开设置 → WorkBuddy →「登录 CodeBuddy」按钮，选「Log in via Chinese Site」"
              "并在浏览器完成即可（也可以双击桌面 CodeBuddy-Login.cmd）。"
              "登错账号：先在浏览器退出旧账号，再点同一个按钮选 /login 重新登录。"
              " / Not signed in: open Settings → WorkBuddy → \"Sign in to CodeBuddy\", pick "
              "\"Log in via Chinese Site\" and finish in the browser (or run CodeBuddy-Login.cmd). "
              "Wrong account? Sign out in the browser first, then use /login in the console that opens.")


def _node_bin():
    """Node used to launch the bundled CLI (it is a #!/usr/bin/env node script,
    so on Windows there is no codebuddy.exe to find on PATH)."""
    override = os.environ.get("WORKBUDDY_NODE_BIN")
    if override and os.path.isfile(override):
        return override
    b = shutil.which("node")
    if b:
        return b
    base = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "node", "versions")
    found = sorted(glob.glob(os.path.join(base, "*", "node.exe")) +
                   glob.glob(os.path.join(base, "*", "bin", "node")))
    return found[-1] if found else None


def _cli_js():
    """The npm-installed *full* CodeBuddy CLI, which has the interactive login
    panel and a normal `dist/codebuddy.js`.

    IMPORTANT: the CLI bundled inside the WorkBuddy app (app.asar.unpacked/cli)
    is a headless `lite-wb` build. It has NO login UI and always talks to the
    desktop-only `www.workbuddy.cn` credential store, so even a successful
    CodeBuddy-Login.cmd sign-in is invisible to it -- "Authentication required"
    forever. Never pick it while a full CLI exists.

    Don't resolve the full CLI relative to `shutil.which("node")`: in the GUI
    process PATH may point at a different node, so that lookup misses and we
    fall back to the useless bundled copy. Scan every known install location
    for the full CLI directly instead; the bundled one is a last resort only.
    """
    override = os.environ.get("WORKBUDDY_CLI_JS")
    if override and os.path.isfile(override):
        return override

    full = []
    npm_rel = os.path.join("node_modules", "@tencent-ai", "codebuddy-code", "bin", "codebuddy")
    # 1) every node version WorkBuddy/this machine installed (22.22.2-6, ...)
    base = os.path.join(os.path.expanduser("~"), ".workbuddy", "binaries", "node", "versions")
    full += sorted(glob.glob(os.path.join(base, "*", npm_rel)), reverse=True)
    # 2) global npm installs
    if IS_WIN:
        appdata = os.environ.get("APPDATA")
        if appdata:
            full.append(os.path.join(appdata, "npm", npm_rel))
    else:
        full += ["/usr/local/lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy",
                 os.path.expanduser("~/.npm-global/lib/node_modules/@tencent-ai/"
                                    "codebuddy-code/bin/codebuddy")]
    # 3) a full CLI sitting next to whatever node is on PATH (old behaviour)
    node = _node_bin()
    if node:
        full.append(os.path.join(os.path.dirname(node), npm_rel))
    found = next((c for c in full if os.path.isfile(c)), None)
    if found:
        return found

    # 4) last resort: the headless bundled build (can chat only if a full CLI
    #    signed in before, and even then via the desktop endpoint).
    if IS_WIN:
        la = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        bundled = os.path.join(la, "Programs", "WorkBuddy", "resources", "app.asar.unpacked",
                               "cli", "bin", "codebuddy")
    else:
        bundled = next((c for c in [
            "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/bin/codebuddy",
            os.path.expanduser("~/Applications/WorkBuddy.app/Contents/Resources/"
                               "app.asar.unpacked/cli/bin/codebuddy")] if os.path.isfile(c)), None)
    if bundled and os.path.isfile(bundled):
        log("warning: only the headless bundled CodeBuddy CLI was found; install the "
            "full CLI (npm i -g @tencent-ai/codebuddy-code) and run CodeBuddy-Login.cmd")
        return bundled
    return None


def _free_port():
    """The CLI opens a local gateway; the running app already owns its default 8373."""
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    except OSError:
        return 0
    finally:
        s.close()


class WorkBuddy(Claude):
    id = "workbuddy"
    icon = "🧑‍💼"               # the hover button draws its own icon (ui/index.html FICONS)
    name = "WorkBuddy"
    name_zh = "WorkBuddy"
    hover = True
    agent = "workbuddy"
    agent_name = "WorkBuddy"
    project_default = "WorkBuddy"
    settings_path = os.path.join(HOME, "settings.json")
    sock = os.environ.get("PARCELWIDGET_WORKBUDDY_SOCK") or os.path.join(instance.BASE, "workbuddy.sock")
    port_file = os.environ.get("PARCELWIDGET_WORKBUDDY_PORT") or os.path.join(instance.BASE, "workbuddy.port")

    def _cli_settings_path(self):
        """The bundled CLI keeps its settings in ~/.codebuddy, not in the app's
        ~/.workbuddy (CODEBUDDY_CONFIG_DIR overrides it)."""
        d = os.environ.get("CODEBUDDY_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".codebuddy")
        return os.path.join(d, "settings.json")

    def start(self):
        super().start()
        if not (self.cfg.get("enabled") and self._bin()):
            return
        # The CLI doesn't read the hooks in ~/.workbuddy/settings.json, so a run
        # started in her balloon would have nobody to answer its permission
        # requests or multiple-choice questions. install() keeps a backup and
        # leaves any other hooks in that file alone.
        try:
            install(self._cli_settings_path(), self.agent)
        except Exception as e:
            log("%s: couldn't install CLI hooks: %r" % (self.id, e))

    # ---------- the chat in her balloon (features/chat.py) ----------
    def _bin(self):
        """Truthy when WorkBuddy's bundled CLI is available: chatView then shows
        the folder picker and the input box (ui/index.html checks state.cli)."""
        return _node_bin() if _cli_js() else None

    def _stdin(self, turn):
        return turn["q"]        # stdin, not an argument: safe for & | < > % " in the text

    def _cmd(self, b, turn, cwd):
        cmd = [b, _cli_js(), "-p", "--port", str(_free_port()),
               "--output-format", "stream-json", "--verbose"]
        # CodeBuddy's model ids differ from Claude's, so keep its default model.
        if self.chat.get("sid"):
            cmd += ["--resume", self.chat["sid"]]
        return cmd

    def _env(self, b):
        # Parcel Widget is launched from inside the WorkBuddy desktop app, so
        # os.environ is full of host-injected variables (CODEBUDDY_HOST,
        # WORKBUDDY_CONFIG_DIR, ACC_PRODUCT_CONFIG_PATH, ...). If any of those
        # reach the CLI it thinks it IS the desktop app: it switches to the
        # www.workbuddy.cn endpoint and reads the desktop-only credential store
        # (auth/workbuddy-desktop.info -> "missing-key"), ignoring the sign-in
        # done by CodeBuddy-Login.cmd. Result: a permanent "Authentication
        # required" even right after a successful browser login, plus MCP
        # "Connection closed" errors from the host's MCP config.
        #
        # Verified: the SAME CLI, launched with only the minimal OS variables a
        # double-clicked .cmd gets, uses copilot.tencent.com and replies OK.
        # So build the child environment from a whitelist instead of inheriting
        # os.environ (a blacklist missed variables and still failed in the GUI).
        keep = ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE",
                "HOMEPATH", "HOMEDRIVE", "APPDATA", "LOCALAPPDATA", "ComSpec",
                "COMSPEC", "NUMBER_OF_PROCESSORS", "PATHEXT", "OS", "LANG",
                "LC_ALL", "NODE_EXTRA_CA_CERTS")
        env = {k: v for k, v in os.environ.items() if k in keep}
        # node's directory must be on PATH for spawned shell/helper commands
        env["PATH"] = os.pathsep.join([os.environ.get("PATH", ""), os.path.dirname(b)])
        env["PARCELWIDGET_RUN"] = "1"        # hook marks these runs as hers
        # The full npm CLI loads dist/codebuddy.js by default; forcing the
        # lite-wb bundle on it would strip its TUI again. Only the app's own
        # bundled headless build needs this variable (its shim otherwise
        # requires a dist/codebuddy that isn't shipped).
        cli = (_cli_js() or "").replace("\\", "/")
        if "app.asar.unpacked" in cli:
            env["CODEBUDDY_FORCE_LITE_WB_BUNDLE"] = "1"
        log("%s: chat env keys=%s cli=%s" % (
            self.id, ",".join(sorted(k for k in env if k.startswith("CODEBUDDY")
                                     or k in ("ACC_PRODUCT_CONFIG_PATH", "WORKBUDDY_CONFIG_DIR"))), cli))
        return env

    def _on_stream(self, m, turn):
        super()._on_stream(m, turn)
        if m.get("type") != "result" or not m.get("is_error"):
            return
        errs = " ".join(str(x) for x in (m.get("errors") or []))[:300]
        low = errs.lower()
        if "cannot find module" in low or "module_not_found" in low or "codebuddy-lite-wb" in low:
            turn["a"] = ("WorkBuddy 的 CLI 产物不匹配：请重开一次桌面 CodeBuddy-Login.cmd，"
                         "并确认 CODEBUDDY_FORCE_LITE_WB_BUNDLE=1 已设置。"
                         " / CLI bundle mismatch: reopen CodeBuddy-Login.cmd first.")
        elif "authentication required" in low or "/login" in low:
            turn["a"] = LOGIN_HINT
        elif not turn["a"] and errs:
            turn["a"] = errs
        elif not turn["a"]:
            # an assistant message said why it stopped, but result carried no text
            turn["a"] = (turn.get("step") or "Run stopped with an error.")[:300]

    def usage_refresh(self, min_age=60):
        pass                    # CodeBuddy has no `/usage` equivalent here

    # ---------- sign in (opens the full CLI's interactive login panel) ----------
    def api_login(self, switch=False):
        """Open a terminal running the FULL CodeBuddy CLI so the user can sign in.

        Login is an interactive TUI (/login -> "Select login method" -> browser),
        which is why the non-interactive chat CLI can't do it itself. Rather than
        make the user hunt for a .cmd file on the Desktop, launch it right here,
        with the same clean environment the chat uses (so the credentials land in
        ~/.codebuddy and are picked up on the next chat). `switch` runs /logout
        first for changing accounts.
        """
        import subprocess
        node, cli = _node_bin(), _cli_js()
        if not node or not cli or not os.path.isfile(cli):
            log("login: no full CodeBuddy CLI found")
            return False
        env = self._env(node)
        env.pop("CODEBUDDY_FORCE_LITE_WB_BUNDLE", None)   # full TUI, not headless
        # A fresh, visible console window with the interactive CLI, in the SAME
        # clean environment the chat uses -- otherwise it would sign in against
        # the desktop endpoint and the chat still couldn't see the credentials.
        # If already signed in it opens a chat; the user runs /login (or /logout
        # then /login) there.
        if IS_WIN:
            hint = ("CodeBuddy sign-in: pick 'Log in via Chinese Site' in the panel, "
                    "then finish in the browser. Type /exit when done.")
            cmd = 'echo %s && "%s" "%s" --port 0' % (hint, node, cli)
            # CREATE_NEW_CONSOLE gives it its own window; use the clean env.
            subprocess.Popen(["cmd", "/c", cmd], env=env,
                             creationflags=0x00000010, close_fds=True)
        else:
            subprocess.Popen([node, cli, "--port", "0"], env=env, close_fds=True)
        log("login: launched full CLI console (switch=%s)" % bool(switch))
        return True

    # ---------- app link, state ----------
    def api_open_claude(self):
        """the "Open WorkBuddy" link in her balloon (the app registers workbuddy://)"""
        try:
            plat.open_path("workbuddy://home")
        except OSError:
            return False
        return True

    def has_app(self):
        return os.path.isdir(HOME)

    def state(self):
        # chat_state() carries cli / chat / folders / running; without it the
        # page has no folder picker, no input box and no turns to draw.
        return dict(self.chat_state(), listening=self.listening,
                    enabled=bool(self.cfg.get("enabled")), app=self.has_app())

    # ---------- menus and settings ----------
    def menu(self, lang):
        T = L.get(lang, L["en"])
        return [{"title": T["on"] if self.listening else T["off"], "info": True},
                {"sep": True},
                {"title": T["chat"], "key": "workbuddy:show"},
                {"title": T["login"], "key": "workbuddy:login"},
                {"title": T["open"], "key": "workbuddy:open"},
                {"title": T["settings"], "key": "workbuddy:settings"}]

    def handle(self, action, arg=""):
        if action == "settings":
            self.app.open_settings("workbuddy")
        elif action == "login":
            self.api_login()
        elif action == "open":
            self.api_open_claude()
        elif action == "show":
            self.app.show_window()
            self.app.page_call("openFeature('workbuddy')")

    def get_settings(self):
        return {"enabled": bool(self.cfg.get("enabled")), "installed": installed(self.settings_path),
                "listening": self.listening, "app": self.has_app(), "cli": bool(self._bin()),
                "cli_path": _cli_js() or "",
                "done": bool(self._c("done", True)), "permissions": bool(self._c("permissions", True)),
                "questions": bool(self._c("questions", True)), "wait": self.wait(),
                "waits": [60, 120, 300, 600], "settings_path": plat.home_short(self.settings_path)}

    def save_settings(self, s):
        s = {k: v for k, v in (s or {}).items() if k in ("enabled", "done", "permissions", "questions", "wait")}
        super().save_settings(s)
