"""macOS: the menu bar icon, and the same menu when you right-click the character.

The icon is a little parcel box with cat ears, followed by the number of packages.
The menu itself is data from menus.py; it is rebuilt every time it opens, so checkmarks,
counts and language are always current. Clicks run on a worker thread: talking to the
web view from the main (menu) thread would deadlock.
"""
import threading

import AppKit
from PyObjCTools import AppHelper

import menus

NSApplicationActivationPolicyAccessory = 1  # no Dock icon, no app menu
NSVariableStatusItemLength = -1


def hide_dock_icon():
    """Call before webview.start(): the Dock icon then never shows up."""
    import webview.platforms.cocoa  # noqa: F401  (it sets the "regular" policy on import)
    AppKit.NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def activate():
    """Bring our windows to the front (an accessory app isn't activated by clicks on the menu)."""
    AppHelper.callAfter(lambda: AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True))


def cat_box_icon():
    """A parcel box with cat ears and a small face, drawn as a template image
    (black + alpha) so macOS tints it for light / dark menu bars."""
    P = AppKit.NSBezierPath

    def draw(rect):
        AppKit.NSColor.blackColor().set()
        box = P.bezierPathWithRoundedRect_xRadius_yRadius_(((2.75, 1.25), (14.5, 9.5)), 2.2, 2.2)
        box.setLineWidth_(1.5)
        box.stroke()
        lid = P.bezierPath()
        lid.moveToPoint_((2.75, 8.2))
        lid.lineToPoint_((17.25, 8.2))
        lid.setLineWidth_(1.1)
        lid.stroke()
        for a, tip, b in (((3.4, 9.6), (5.0, 15.2), (8.4, 10.6)), ((11.6, 10.6), (15.0, 15.2), (16.6, 9.6))):
            e = P.bezierPath()
            e.moveToPoint_(a)
            e.lineToPoint_(tip)
            e.lineToPoint_(b)
            e.closePath()
            e.setLineJoinStyle_(AppKit.NSLineJoinStyleRound)
            e.setLineWidth_(0.8)
            e.fill()
            e.stroke()
        for x in (7.4, 12.6):
            P.bezierPathWithOvalInRect_(((x - 0.95, 5.0), (1.9, 1.9))).fill()
        m = P.bezierPath()
        m.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_((9.3, 4.1), 0.7, 180, 360, False)
        m.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_((10.7, 4.1), 0.7, 180, 360, False)
        m.setLineWidth_(0.9)
        m.setLineCapStyle_(AppKit.NSLineCapStyleRound)
        m.stroke()
        return True

    img = AppKit.NSImage.imageWithSize_flipped_drawingHandler_((20, 16), False, draw)
    img.setTemplate_(True)
    return img


class _Target(AppKit.NSObject):
    """Receives menu clicks and is the menu's delegate (rebuilds it right before it opens)."""

    def act_(self, sender):
        self.owner.dispatch(sender.representedObject())

    def menuNeedsUpdate_(self, menu):
        self.owner.fill(menu, menus.spec(self.owner.app))


class MenuBar:
    def __init__(self, app):
        self.app = app
        self.item = None
        self._count = (0, 0)

    # ---------- setup (main thread) ----------
    def install(self):
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.target = _Target.alloc().init()
        self.target.owner = self
        self.item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        btn = self.item.button()
        btn.setImage_(cat_box_icon())
        btn.setImagePosition_(AppKit.NSImageLeft)
        self.menu = self._new_menu()
        self.menu.setDelegate_(self.target)
        self.item.setMenu_(self.menu)
        self.fill(self.menu, menus.spec(self.app))
        self._show_count()

    def _new_menu(self, title=""):
        m = AppKit.NSMenu.alloc().initWithTitle_(title)
        m.setAutoenablesItems_(False)
        return m

    # ---------- menu from data ----------
    def fill(self, menu, items):
        menu.removeAllItems()
        for it in items:
            if it.get("sep"):
                menu.addItem_(AppKit.NSMenuItem.separatorItem())
                continue
            key = it.get("key")
            mi = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                it["title"], "act:" if key else None, it.get("shortcut", "") if key else "")
            if key:
                mi.setTarget_(self.target)
                mi.setRepresentedObject_(key)
            mi.setState_(AppKit.NSControlStateValueOn if it.get("checked") else AppKit.NSControlStateValueOff)
            mi.setEnabled_(bool(key or it.get("sub")) and it.get("enabled", True) and not it.get("info"))
            if it.get("sub"):
                sub = self._new_menu(it["title"])
                self.fill(sub, it["sub"])
                mi.setSubmenu_(sub)
            menu.addItem_(mi)

    def popup(self):
        """Show the menu at the mouse (right-click on the character). Thread-safe."""
        def show():
            m = self._new_menu()
            self.fill(m, menus.spec(self.app))
            m.popUpMenuPositioningItem_atLocation_inView_(None, AppKit.NSEvent.mouseLocation(), None)
        AppHelper.callAfter(show)

    def dispatch(self, key):
        threading.Thread(target=menus.handle, args=(self.app, key), daemon=True).start()

    # ---------- count next to the icon ----------
    def _show_count(self):
        n, d = self._count
        self.item.button().setTitle_((" %d" % n if n else "") + (" ✓%d" % d if d else ""))

    def set_count(self, n, delivered):
        """Thread-safe."""
        if (n, delivered) == self._count:
            return
        self._count = (n, delivered)
        if self.item is not None:
            AppHelper.callAfter(self._show_count)
