"""The widget's menu, as data. The same menu is shown by the menu bar icon and by
right-clicking the character (menubar.py draws it on macOS).

    📦 Parcels          ▸  (the feature's own items, e.g. Check Now / Show Packages / Parcel Settings…)
    📊 System           ▸  Show Monitor / Monitor Settings…
    👉 Poke
    ─────────
    ✓ Show Widget
    Settings…          ⌘,
    Quit Parcel Widget ⌘Q

Item: {"title", "key", "checked", "enabled", "shortcut"} | {"title", "sub": [items]} |
      {"title", "info": True} (greyed text) | {"sep": True}
A click sends its key to handle(): "app:<action>" or "<feature id>:<action>".
"""
from core import log

L = {
    "en": {"show": "Show Widget", "settings": "Settings…", "quit": "Quit Parcel Widget"},
    "zh": {"show": "显示小组件", "settings": "设置…", "quit": "退出快递小组件"},
}


def spec(app):
    lang = app.cfg.get("lang", "en")
    T = L.get(lang, L["en"])
    out = []
    for f in app.features:
        title = "%s  %s" % (f.icon, f.name_zh if lang == "zh" else f.name)
        if not f.info().get("hover", True) and f.menu(lang) is None:
            continue            # not available on this system (e.g. USB check outside macOS)
        sub = f.menu(lang)
        if sub:
            out.append({"title": title, "sub": sub})
        else:
            out.append({"title": title, "key": f.id + ":go"})
    out += [
        {"sep": True},
        {"title": T["show"], "key": "app:show", "checked": app.visible},
        {"title": T["settings"], "key": "app:settings", "shortcut": ","},
        {"title": T["quit"], "key": "app:quit", "shortcut": "q"},
    ]
    return out


def handle(app, key):
    """Runs on a worker thread (talking to the web view from the menu's thread would deadlock)."""
    try:
        fid, _, action = key.partition(":")
        if fid == "app":
            if action == "show":
                app.toggle_window()
            elif action == "settings":
                app.open_settings("general")
            elif action == "quit":
                app.quit()
            return
        f = app.feature(fid)
        if f:
            f.handle(action)
        app.push()
    except Exception as ex:
        log("menu action %s failed: %r" % (key, ex))
