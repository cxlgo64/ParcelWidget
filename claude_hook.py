"""Claude Code hook: passes what Claude is doing to Parcel Widget's balloon.

Installed by the widget (Settings → 🤖 Claude) into ~/.claude/settings.json, run by the
system's /usr/bin/python3 (standard library only, Python 3.9+); on Windows by the Python the
widget runs on, or as ParcelWidgetHook.exe next to the packaged app. Claude Code runs it on:
    Stop / StopFailure        Claude finished (or failed): she says how it went; when Claude ended
                              with a question and buttons, your pick goes back to Claude
    Notification              Claude is waiting for you
    PermissionRequest         Claude wants to do something: Allow / Deny from her balloon
    PreToolUse AskUserQuestion  Claude asks you something: pick the answer in her balloon
    PostToolUse               a tool ran: questions already answered in Claude go away

It hands the event to the widget over a local socket (only you can open it; on Windows a
port on this PC only, with a password kept in your own data folder) and, for the last two,
waits for your choice. If the widget isn't running, you answer in Claude, or the
time runs out, it prints nothing: Claude Code then carries on exactly as without it.
"""
import json
import os
import socket
import sys

IS_WIN = sys.platform == "win32"
if IS_WIN:
    BASE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ParcelWidget")
else:
    BASE = os.path.expanduser("~/Library/Application Support/ParcelWidget")
SOCK = os.environ.get("PARCELWIDGET_CLAUDE_SOCK") or os.path.join(BASE, "claude.sock")
PORT_FILE = os.environ.get("PARCELWIDGET_CLAUDE_PORT") or os.path.join(BASE, "claude.port")    # Windows
MAX_TEXT = 4000


def _slim(v, n=MAX_TEXT):
    """keep what the balloon shows; long strings cut"""
    if isinstance(v, str):
        return v if len(v) <= n else v[:n] + "…"
    if isinstance(v, list):
        return [_slim(x, n) for x in v[:50]]
    if isinstance(v, dict):
        return {k: _slim(x, n) for k, x in list(v.items())[:50]}
    return v


def _blocking(ev):
    name = ev.get("hook_event_name")
    return name in ("PermissionRequest", "Stop") or (name == "PreToolUse" and ev.get("tool_name") == "AskUserQuestion")


def _output(ev, ans):
    """the widget's answer -> the JSON Claude Code expects (None: no decision)"""
    name = ev.get("hook_event_name")
    if not isinstance(ans, dict) or ans.get("skip"):
        return None
    if name == "PermissionRequest":
        if ans.get("behavior") == "allow":
            d = {"behavior": "allow"}
            if ans.get("always") and ev.get("permission_suggestions"):
                d["updatedPermissions"] = ev["permission_suggestions"]
            return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": d}}
        if ans.get("behavior") == "deny":
            return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {
                "behavior": "deny", "message": ans.get("message") or "Denied in Parcel Widget."}}}
        return None
    if name == "Stop" and ans.get("choice"):
        # your pick from the buttons Claude offered at the end of its turn: Claude carries on with it
        ask = (" (your answer to: %s)" % ans["ask"]) if ans.get("ask") else ""
        return {"decision": "block",
                "reason": 'The user picked "%s" in Parcel Widget%s. Carry on with that, as if they had pressed '
                          'that button.' % (ans["choice"], ask)}
    if name == "PreToolUse" and isinstance(ans.get("answers"), dict):
        inp = dict(ev.get("tool_input") or {})
        inp["answers"] = {str(k): str(v) for k, v in ans["answers"].items()}
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                       "updatedInput": inp}}
    return None


def _stdin():
    """what Claude Code sent, as UTF-8 whatever the system's own encoding is"""
    try:
        raw = sys.stdin.buffer.read()
    except Exception:           # a program without a console: no sys.stdin, but the pipe is there
        with open(0, "rb", closefd=False) as f:
            raw = f.read()
    return raw.decode("utf-8", "replace")


def _connect():
    """(the connection to the widget, the password to send along or None); OSError if it isn't running"""
    if not IS_WIN:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(SOCK)
        return s, None
    try:
        with open(PORT_FILE, encoding="utf-8") as f:
            d = json.load(f)
        port, token = int(d["port"]), str(d.get("token") or "")
    except (ValueError, KeyError, TypeError):
        raise OSError("bad port file")
    return socket.create_connection(("127.0.0.1", port), timeout=2), token


def main():
    try:
        ev = json.loads(_stdin() or "{}")
    except ValueError:
        return
    if not isinstance(ev, dict) or not ev.get("hook_event_name"):
        return
    blocking = _blocking(ev)
    keep = ("hook_event_name", "session_id", "cwd", "tool_name", "tool_input", "permission_suggestions",
            "last_assistant_message", "message", "title", "notification_type", "error", "permission_mode")
    msg = {k: ev[k] for k in keep if k in ev}
    if not blocking:      # the widget only needs a few fields of other tools' input
        ti = msg.get("tool_input")
        if isinstance(ti, dict) and msg.get("tool_name") != "mcp__ccd_turn__wrap_up":
            msg["tool_input"] = {}
    if isinstance(ev.get("tool_input"), dict):
        import hashlib
        msg["call"] = hashlib.sha1(json.dumps(ev["tool_input"], sort_keys=True).encode()).hexdigest()[:16]
    msg = _slim(msg)
    msg["wait"] = blocking
    if os.environ.get("PARCELWIDGET_RUN"):
        msg["run"] = True      # started from her balloon (Claude小姐)
    try:
        s, token = _connect()
        if token is not None:
            msg["token"] = token
        s.sendall((json.dumps(msg) + "\n").encode())
    except OSError:
        return              # the widget isn't running: nothing to do
    if not blocking:
        s.close()
        return
    s.settimeout(None)      # the widget decides how long to wait, then answers or hangs up
    try:
        line = s.makefile("r", encoding="utf-8").readline()
    except OSError:
        return
    finally:
        try:
            s.close()
        except OSError:
            pass
    try:
        out = _output(ev, json.loads(line)) if line.strip() else None
    except ValueError:
        out = None
    if out:
        text = json.dumps(out)          # plain ASCII
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            os.write(1, text.encode())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass               # never get in Claude's way
    sys.exit(0)
