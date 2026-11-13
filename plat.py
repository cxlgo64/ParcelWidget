"""What differs between macOS and Windows in small ways: opening things, file locks, running
helper programs without a console window flashing up, PowerShell.

Bigger platform pieces have their own modules:
    macOS     menubar.py (menu bar icon), power.py, airprint.py, usbscan.py
    Windows   wintray.py (tray icon), power.py, winprint.py, usbscan_win.py

No imports from the rest of the widget here: instance.py uses this before anything else exists.
"""
import base64
import os
import subprocess
import sys
import time

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# Windows: a program without a console (the packaged widget, pythonw) gets a console window for
# every command line tool it starts, unless told otherwise. Pass **HIDE to subprocess calls.
HIDE = {"creationflags": 0x08000000} if IS_WIN else {}      # CREATE_NO_WINDOW


# ---------------- opening things ----------------
def open_path(path):
    """open a file, a folder, or an address like ms-settings:printers with whatever handles it"""
    if IS_WIN:
        os.startfile(path)      # noqa: S606 - the shell's "open", like double-clicking it
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_url(url):
    import webbrowser
    webbrowser.open(url)


def reveal(path):
    """show a file in Finder / Explorer, selected"""
    if IS_WIN:
        subprocess.Popen('explorer /select,"%s"' % os.path.normpath(path))
    elif IS_MAC:
        subprocess.Popen(["open", "-R", path])


def base_name(path):
    """the last part of a folder path, whichever way its slashes lean"""
    p = str(path or "").rstrip("/\\")
    return p.replace("\\", "/").rsplit("/", 1)[-1] or p


def home_short(path):
    """/Users/me/x -> ~/x, C:\\Users\\me\\x -> ~\\x (for showing)"""
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home) else path


# ---------------- file locks (one copy of the widget at a time holds one) ----------------
def lock_file(f, wait=0.0):
    """lock an open file for this process. False if another process holds it (after waiting up
    to `wait` seconds). The system lets go of it when the process ends, however it ends."""
    end = time.time() + wait
    while True:
        try:
            if IS_WIN:
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if time.time() >= end:
                return False
            time.sleep(0.1)


def unlock_file(f):
    try:
        if IS_WIN:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        pass


# ---------------- PowerShell (Windows) ----------------
_PS_HEAD = ("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';"
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$OutputEncoding=[Text.Encoding]::UTF8;")


def powershell_exe():
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.exists(p) else "powershell.exe"


def powershell(script, args=(), timeout=60, elevate=False):
    """run a PowerShell script (Windows PowerShell 5.1, part of Windows): (exit code, stdout, stderr).
    args reach the script as $env:PW_ARG0, $env:PW_ARG1, ... so nothing typed by the user is
    ever part of the script text. Output is UTF-8. elevate: ask for administrator rights (the
    Windows "Do you want to allow…" prompt); then there is no output, only the exit code."""
    env = dict(os.environ)
    for i, a in enumerate(args):
        env["PW_ARG%d" % i] = str(a)
    if elevate:
        # the elevated copy doesn't get our environment: its arguments travel inside the script
        pre = "".join("$env:PW_ARG%d=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'));"
                      % (i, base64.b64encode(str(a).encode("utf-8")).decode()) for i, a in enumerate(args))
        inner = base64.b64encode((_PS_HEAD + pre + script).encode("utf-16-le")).decode()
        script = ("$p = Start-Process -FilePath '%s' -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList "
                  "'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand','%s'; exit $p.ExitCode"
                  % (powershell_exe(), inner))
    enc = base64.b64encode((_PS_HEAD + script).encode("utf-16-le")).decode()
    try:
        p = subprocess.run([powershell_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc], capture_output=True, timeout=timeout, env=env,
                           stdin=subprocess.DEVNULL, **HIDE)
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except Exception as e:
        return 1, "", str(e)
    return p.returncode, p.stdout.decode("utf-8", "replace"), _ps_err(p.stderr.decode("utf-8", "replace"))


def _ps_err(text):
    """PowerShell wraps errors in XML when its output is piped ("#< CLIXML ..."): the message"""
    if "CLIXML" not in text:
        return text.strip()
    import html
    import re
    parts = re.findall(r'<S S="Error">(.*?)</S>', text, re.S)
    msg = html.unescape("".join(parts)).replace("_x000D__x000A_", "\n")
    return msg.strip() or text.strip()
