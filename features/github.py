"""GitHub: your repositories and notifications in her balloon.

It asks GitHub through the GitHub command line (`gh`), signed in as you: the widget never sees
or keeps a token (gh keeps its own sign-in). Not installed or not signed in -> she says how to
set it up (`brew install gh`, on Windows `winget install GitHub.cli`, then `gh auth login` in a terminal).

What she shows:
  - your repositories, latest push first: private or public, language, stars, forks, open
    issues and pull requests, whether the checks on the default branch passed
  - your unread notifications (review requests, mentions, issues on your repos…)
  - the copies of them on this computer (looked for in a few usual folders): uncommitted files and
    commits not pushed yet (as of your last fetch: she doesn't fetch)

It checks when you open her GitHub balloon (and every `every` minutes if you ask for it in
Settings); with "notify" on, she tells you when new notifications come in.
"""
import json
import os
import re
import subprocess
import threading
import time

import plat
from core import HIDE, IS_WIN, log, save_config

from . import Feature
from .chat import which

if IS_WIN:
    GH_BINS = [os.path.join(os.environ.get(v) or "C:\\", "GitHub CLI", "gh.exe")
               for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
else:
    GH_BINS = ["/opt/homebrew/bin/gh", "/usr/local/bin/gh"]
EVERYS = [0, 15, 30, 60]          # minutes between checks in the background (0: only when you open her balloon)
ROOTS = ["~/Downloads", "~/Documents", "~/Developer", "~/Projects", "~/code", "~/GitHub", "~/src", "~/Desktop"]
if IS_WIN:      # where Visual Studio and GitHub Desktop put them
    ROOTS += ["~/source/repos", "~/Documents/GitHub"]
SKIP_DIRS = {"node_modules", ".venv", "venv", "Library", "build", "dist", ".git", "__pycache__", "Pods", "AppData"}

QUERY = """query { viewer { login name url
  repositories(first: 60, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) { totalCount nodes {
    name nameWithOwner description url isPrivate isFork isArchived stargazerCount forkCount pushedAt
    primaryLanguage { name color }
    issues(states: OPEN) { totalCount } pullRequests(states: OPEN) { totalCount }
    defaultBranchRef { name target { ... on Commit { statusCheckRollup { state } } } } } } } }"""

L = {
    "en": {"open": "Show my repositories", "settings": "GitHub Settings…", "web": "Open GitHub",
           "none": "GitHub command line (gh) isn't installed"},
    "zh": {"open": "看看我的仓库", "settings": "GitHub 设置…", "web": "打开 GitHub",
           "none": "没有安装 GitHub 命令行（gh）"},
}


def _web_url(api_url, kind):
    """a notification's API link -> the page on github.com"""
    m = re.match(r"https://api\.github\.com/repos/([^/]+/[^/]+)/(issues|pulls|commits|releases)/(\w+)", api_url or "")
    if not m:
        return None
    repo, what, n = m.groups()
    if what == "pulls":
        return "https://github.com/%s/pull/%s" % (repo, n)
    if what == "issues":
        return "https://github.com/%s/issues/%s" % (repo, n)
    if what == "commits":
        return "https://github.com/%s/commit/%s" % (repo, n)
    return "https://github.com/%s/releases" % repo


def _ts(iso):
    try:
        import calendar
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


class GitHub(Feature):
    id = "github"
    icon = "🐙"                 # the hover button draws GitHub's mark instead (ui/index.html FICONS)
    name = "GitHub"
    name_zh = "GitHub"
    hover = True

    def __init__(self, app):
        super().__init__(app)
        self.data = {"st": "unknown", "login": "", "url": "", "repos": [], "total": 0, "notifs": [], "err": ""}
        self.local = {}            # "owner/name" -> {path, branch, dirty, ahead, behind}
        self.busy = False
        self.last = 0
        self._local_ts = 0
        self._seen = set()         # notification ids already told about
        self._lock = threading.Lock()

    # ---------- settings ----------
    def every(self):
        v = self.cfg.get("every", 0)
        return v if v in EVERYS else 0

    def roots(self):
        r = self.cfg.get("roots")
        return [x for x in (r if isinstance(r, list) else ROOTS) if isinstance(x, str) and x.strip()][:12]

    def _bin(self):
        return which("gh", GH_BINS)

    def _gh(self, args, timeout=40):
        b = self._bin()
        extra = [os.path.dirname(b or "")] + ([] if IS_WIN else ["/usr/bin", "/bin"])
        env = dict(os.environ, PATH=os.pathsep.join([os.environ.get("PATH", "")] + extra),
                   GH_PROMPT_DISABLED="1", NO_COLOR="1")
        return subprocess.run([b] + args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=env, stdin=subprocess.DEVNULL, **HIDE)

    # ---------- checking ----------
    def tick(self, now):
        e = self.every()
        if e and self.cfg.get("used") and now - self.last > e * 60:
            self.refresh()

    def refresh(self, manual=False):
        with self._lock:
            if self.busy:
                return
            self.busy = True
        self.app.push_soon()
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual):
        try:
            if not self._bin():
                self.data = dict(self.data, st="no_gh")
                return
            r = self._gh(["api", "graphql", "-f", "query=" + QUERY])
            if r.returncode != 0:
                err = (r.stderr or "").strip()
                st = "signed_out" if re.search(r"auth login|not logged|401|Bad credentials", err, re.I) else "error"
                self.data = dict(self.data, st=st, err=err.splitlines()[-1][:200] if err else "exit %s" % r.returncode)
                log("github: check failed (%s)" % st)
                return
            v = (json.loads(r.stdout).get("data") or {}).get("viewer") or {}
            repos = []
            for n in (v.get("repositories") or {}).get("nodes") or []:
                tgt = ((n.get("defaultBranchRef") or {}).get("target") or {})
                ci = ((tgt.get("statusCheckRollup") or {}).get("state") or "").lower()
                lang = n.get("primaryLanguage") or {}
                repos.append({"name": n["name"], "full": n["nameWithOwner"], "desc": (n.get("description") or "")[:200],
                              "url": n["url"], "private": n.get("isPrivate"), "fork": n.get("isFork"),
                              "archived": n.get("isArchived"), "stars": n.get("stargazerCount", 0),
                              "forks": n.get("forkCount", 0), "pushed": _ts(n.get("pushedAt")),
                              "lang": lang.get("name") or "", "color": lang.get("color") or "",
                              "issues": (n.get("issues") or {}).get("totalCount", 0),
                              "prs": (n.get("pullRequests") or {}).get("totalCount", 0), "ci": ci})
            notifs = self._notifications()
            self.data = {"st": "ok", "login": v.get("login") or "", "url": v.get("url") or "", "name": v.get("name") or "",
                         "repos": repos, "total": (v.get("repositories") or {}).get("totalCount", len(repos)),
                         "notifs": notifs, "err": ""}
            self._tell(notifs, manual)
            if time.time() - self._local_ts > 300 or manual:
                self.local = self._find_local({r["full"].lower() for r in repos})
                self._local_ts = time.time()
            log("github: %d repositories, %d unread" % (len(repos), len(notifs)))
        except subprocess.TimeoutExpired:
            self.data = dict(self.data, st="error", err="timeout")
        except Exception as e:
            self.data = dict(self.data, st="error", err=type(e).__name__)
            log("github: check failed %r" % type(e).__name__)
        finally:
            self.last = time.time()
            self.busy = False
            self.app.push_soon()

    def _notifications(self):
        r = self._gh(["api", "notifications?per_page=30"], timeout=30)
        if r.returncode != 0:
            return []
        out = []
        for n in json.loads(r.stdout or "[]"):
            s = n.get("subject") or {}
            repo = (n.get("repository") or {}).get("full_name") or ""
            out.append({"id": str(n.get("id")), "repo": repo, "title": (s.get("title") or "")[:200],
                        "type": s.get("type") or "", "why": n.get("reason") or "", "ts": _ts(n.get("updated_at")),
                        "url": _web_url(s.get("url"), s.get("type")) or ("https://github.com/" + repo if repo else
                                                                         "https://github.com/notifications")})
        return out

    def _tell(self, notifs, manual):
        """a balloon for notifications that are new since she last looked (only with "notify" on)"""
        new = [n for n in notifs if n["id"] not in self._seen]
        first = not self._seen and not getattr(self, "_told_once", False)
        self._seen |= {n["id"] for n in notifs}
        self._told_once = True
        if new and not first and not manual and self.cfg.get("notify"):
            self.app.reports.add(self.id, "notifs", {"items": new[:5], "n": len(new)}, live=False)

    def _find_local(self, wanted):
        """copies of your repositories on this computer: a few folders deep in the usual places"""
        found = {}
        for root in self.roots():
            root = os.path.normpath(os.path.expanduser(root))
            if not os.path.isdir(root):
                continue
            base = root.count(os.sep)
            for d, dirs, _ in os.walk(root):
                if d.count(os.sep) - base >= 3:
                    dirs[:] = []
                    continue
                if ".git" in dirs:
                    full = self._remote(d)
                    if full and full in wanted and full not in found:
                        found[full] = self._git_state(d)
                    dirs[:] = []
                    continue
                dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        return found

    @staticmethod
    def _remote(path):
        try:
            with open(os.path.join(path, ".git", "config"), encoding="utf-8", errors="replace") as f:
                m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s*$", f.read(), re.M)
            return m.group(1).lower() if m else None
        except OSError:
            return None

    @staticmethod
    def _git_state(path):
        st = {"path": path, "name": os.path.basename(path), "branch": "", "dirty": 0, "ahead": 0, "behind": 0}
        try:
            r = subprocess.run(["git", "-C", path, "status", "--porcelain=v1", "-b"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=10,
                               stdin=subprocess.DEVNULL, **HIDE)
            lines = r.stdout.splitlines()
            if lines and lines[0].startswith("## "):
                head = lines.pop(0)[3:]
                st["branch"] = head.split("...")[0].split(" ")[0]
                for k in ("ahead", "behind"):
                    m = re.search(k + r" (\d+)", head)
                    st[k] = int(m.group(1)) if m else 0
            st["dirty"] = len([x for x in lines if x.strip()])
        except Exception:
            pass
        return st

    # ---------- her balloon ----------
    def api_opened(self):
        if not self.cfg.get("used"):
            self.cfg["used"] = True
            save_config(self.app.cfg)
        if time.time() - self.last > 120:
            self.refresh(manual=True)
        return True

    def api_refresh(self):
        self.refresh(manual=True)
        return True

    def api_open(self, url):
        if isinstance(url, str) and url.startswith("https://github.com/"):
            plat.open_url(url)
        return True

    def api_reveal(self, full):
        st = self.local.get((full or "").lower())
        if st and os.path.isdir(st["path"]):
            plat.open_path(st["path"])
        return True

    def state(self):
        d = self.data
        show = [r for r in d["repos"] if (self.cfg.get("forks") or not r["fork"]) and
                (self.cfg.get("archived") or not r["archived"])]
        for r in show:
            loc = self.local.get(r["full"].lower())
            r["local"] = {k: loc[k] for k in ("name", "branch", "dirty", "ahead", "behind")} if loc else None
        return {"st": d["st"], "login": d["login"], "url": d["url"], "repos": show, "total": d["total"],
                "hidden": len(d["repos"]) - len(show), "notifs": d["notifs"][:10], "unread": len(d["notifs"]),
                "err": d.get("err", ""), "busy": self.busy, "last": self.last, "gh": bool(self._bin())}

    # ---------- menus ----------
    def menu(self, lang):
        T = L.get(lang, L["en"])
        if not self._bin():
            return [{"title": T["none"], "info": True}]
        return [{"title": T["open"], "key": "github:show"}, {"title": T["web"], "key": "github:web"},
                {"title": T["settings"], "key": "github:settings"}]

    def handle(self, action, arg=""):
        if action == "settings":
            self.app.open_settings("github")
        elif action == "web":
            plat.open_url(self.data.get("url") or "https://github.com")
        else:
            self.app.show_window()
            self.app.page_call("openFeature('github')")

    def get_settings(self):
        return {"login": self.data.get("login") or "", "st": self.data.get("st"), "gh": bool(self._bin()),
                "forks": bool(self.cfg.get("forks")), "archived": bool(self.cfg.get("archived")),
                "notify": bool(self.cfg.get("notify")), "every": self.every(), "everys": EVERYS,
                "roots": self.roots()}

    def save_settings(self, s):
        for k in ("forks", "archived", "notify"):
            if k in s:
                self.cfg[k] = bool(s[k])
        if s.get("every") in EVERYS:
            self.cfg["every"] = s["every"]
        if isinstance(s.get("roots"), list):
            self.cfg["roots"] = [x.strip() for x in s["roots"] if isinstance(x, str) and x.strip()][:12]
            self._local_ts = 0
