"""Features: the little jobs the character does for you.

Each feature is a class with:
    id, icon, name, name_zh      shown on her hover buttons, in the menus and the settings window
    hover = True                 gets a button around her when you hover over her (idle mode)
    start()                      called once at launch (start threads, run the first check)
    tick(now)                    called every ~15 s by the scheduler (run jobs that are due);
                                 not called while the computer is asleep
    sleep() / wake()             the computer goes to sleep / wakes up
    state() -> dict              sent to the pages as state["f"][id]
    menu(L) -> [items]           its submenu in the menu bar / right-click menu (see menus.py)
    handle(action, arg)          a menu click "<id>:<action>" lands here
    get_settings() / save_settings(dict)   its tab in the settings window

A feature reports what it did with app.reports (see reports.py): a report shows up in her
speech balloon until you confirm it. The page side of a feature (its balloon contents) is in
ui/index.html under FEATURES[id].

To add a feature: write features/<name>.py, add it to make_features() below, add its page
side to FEATURES in ui/index.html and its settings tab to ui/settings.html.
"""


class Feature:
    id = ""
    icon = ""
    name = ""
    name_zh = ""
    hover = True

    def __init__(self, app):
        self.app = app

    @property
    def cfg(self):
        return self.app.cfg.setdefault(self.id, {})

    def start(self):
        pass

    def tick(self, now):
        pass

    def stop(self):
        """turned off in Settings → Features (start() runs again if it's turned back on)"""
        pass

    def sleep(self):
        pass

    def wake(self):
        pass

    def state(self):
        return {}

    def menu(self, L):
        return []

    def handle(self, action, arg=""):
        pass

    def get_settings(self):
        return dict(self.cfg)

    def save_settings(self, s):
        self.cfg.update(s)

    def info(self):
        hidden = self.id in (self.app.cfg.get("features_hidden") or [])
        return {"id": self.id, "icon": self.icon, "name": self.name, "name_zh": self.name_zh,
                "hover": self.hover and not hidden, "available": True}


def make_features(app):
    from .claude import Claude
    from .codex import Codex
    from .github import GitHub
    from .mail import Mail
    from .parcels import Parcels
    from .poke import Poke
    from .sysmon import SysMon
    from .usb import USB
    # order = order of her hover buttons and of the menus
    return [Parcels(app), Mail(app), SysMon(app), USB(app), Claude(app), Codex(app), GitHub(app), Poke(app)]
