"""Reports: what a feature tells you in her speech balloon.

A report is data, not text: {"id", "feature", "kind", "ts", "live", "hidden", "data": {...}}.
The page turns it into words in the current language (ui/index.html, FEATURES[id].report).

    live    still running: the balloon shows the progress
    hidden  not shown yet (an automatic check only speaks up if something changed)

A report stays until you confirm it (✓); when none are left she goes idle.
"""
import copy
import threading
import time


class Reports:
    def __init__(self, on_change=lambda: None):
        self.lock = threading.Lock()
        self.items = []
        self._next = 1
        self.on_change = on_change

    def add(self, feature, kind, data=None, live=True, hidden=False):
        with self.lock:
            r = {"id": self._next, "feature": feature, "kind": kind, "ts": time.time(),
                 "live": live, "hidden": hidden, "data": data or {}}
            self._next += 1
            self.items.append(r)
        self.on_change()
        return r

    def set(self, r, key, value):
        """Change one field of a report's data (called from worker threads)."""
        with self.lock:
            r["data"][key] = value
        self.on_change()

    def finish(self, r, **fields):
        with self.lock:
            r.update(fields)
            r["live"] = False
            r["ts"] = time.time()
        self.on_change()

    def drop(self, r):
        with self.lock:
            if r in self.items:
                self.items.remove(r)
        self.on_change()

    def ack(self, rid):
        """You confirmed it (✓). Live reports can't be confirmed yet."""
        with self.lock:
            for r in self.items:
                if r["id"] == rid and not r["live"]:
                    self.items.remove(r)
                    break
        self.on_change()
        return True

    def ack_all(self):
        with self.lock:
            self.items = [r for r in self.items if r["live"]]
        self.on_change()

    def visible(self):
        with self.lock:
            return copy.deepcopy([r for r in self.items if not r["hidden"]])
