"""Poke: she does a random move and says something. Lives on the page (ui/index.html);
the backend only gives it a hover button and a menu item."""
from . import Feature

L = {"en": "Poke", "zh": "戳一戳"}


class Poke(Feature):
    id = "poke"
    icon = "👉"
    name = "Poke"
    name_zh = "戳一戳"

    def menu(self, lang):
        return None   # a single item, no submenu (see menus.py)

    def handle(self, action, arg=""):
        self.app.show_window()
        self.app.page_call("openFeature('poke')")
