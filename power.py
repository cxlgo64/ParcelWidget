"""Sleep / wake of the computer.

macOS: NSWorkspace sends "will sleep" and "did wake" only for a real sleep and a real wake
(lid open, key press). While asleep, macOS still wakes the Mac for a few seconds now and then
(DarkWake / Power Nap) and our threads run during those - so features must not trust their
own clock to know whether the computer is in use: they check `asleep` instead.
"""
from core import IS_MAC, log

_observer = None   # kept alive: NSNotificationCenter doesn't retain observers


def watch(on_sleep, on_wake):
    """Call on_sleep() / on_wake() (on the main thread) when the computer sleeps / wakes."""
    global _observer
    if not IS_MAC:
        return False
    import AppKit

    class _PowerObserver(AppKit.NSObject):
        def willSleep_(self, note):
            on_sleep()

        def didWake_(self, note):
            on_wake()

    _observer = _PowerObserver.alloc().init()
    nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
    nc.addObserver_selector_name_object_(_observer, "willSleep:",
                                         AppKit.NSWorkspaceWillSleepNotification, None)
    nc.addObserver_selector_name_object_(_observer, "didWake:",
                                         AppKit.NSWorkspaceDidWakeNotification, None)
    log("watching sleep / wake")
    return True
