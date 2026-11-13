"""Sleep / wake of the computer.

macOS: NSWorkspace sends "will sleep" and "did wake" only for a real sleep and a real wake
(lid open, key press). While asleep, macOS still wakes the Mac for a few seconds now and then
(DarkWake / Power Nap) and our threads run during those - so features must not trust their
own clock to know whether the computer is in use: they check `asleep` instead.

Windows: .NET's SystemEvents.PowerModeChanged says Suspend when the PC goes to sleep or
hibernates and Resume when it's back (pythonnet is there already: pywebview's window uses it).
"""
from core import IS_MAC, IS_WIN, log

_observer = None   # kept alive: NSNotificationCenter doesn't retain observers


def watch(on_sleep, on_wake):
    """Call on_sleep() / on_wake() (on the main thread) when the computer sleeps / wakes."""
    global _observer
    if IS_WIN:
        return _watch_win(on_sleep, on_wake)
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


def _watch_win(on_sleep, on_wake):
    global _observer
    try:
        import clr
        try:
            clr.AddReference("Microsoft.Win32.SystemEvents")     # its own assembly on newer .NET
        except Exception:
            pass
        from Microsoft.Win32 import PowerModes, SystemEvents
    except Exception as ex:
        log("can't watch sleep / wake: %r" % ex)
        return False

    def changed(sender, e):
        try:
            if e.Mode == PowerModes.Suspend:
                on_sleep()
            elif e.Mode == PowerModes.Resume:
                on_wake()
        except Exception as ex:
            log("sleep / wake error %r" % ex)

    _observer = changed
    SystemEvents.PowerModeChanged += changed
    log("watching sleep / wake")
    return True
