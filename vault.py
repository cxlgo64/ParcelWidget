"""Saved passwords and API keys: an encrypted file, unlocked with Touch ID (macOS) or Windows Hello.

Why not the Keychain: the widget isn't signed with a fixed certificate, so every new build (and
every Python update) is a "different app" to the Keychain, which then asks again and again.

How it works
  - One file for all copies of the widget: secrets.vault in the main data folder.
  - The secrets are encrypted (AES-256-CBC + HMAC-SHA256, encrypt-then-MAC) with a key derived
    from this Mac's hardware ID and a random salt (PBKDF2, 200k rounds): the file is useless
    on another computer or in a backup restored elsewhere.
  - Before the first secret is used, she asks for Touch ID (or the Mac's password when Touch
    ID isn't available, e.g. lid closed) - once per launch. Turned off in Settings → General,
    she never asks.
  - The names of the saved items are not secret (so the pages can show "saved" without asking).
  - Honest limits: the Touch ID check is a lock inside the widget. A program running as you on
    this Mac could still decrypt the file. The Keychain kept other programs out but asked every
    time; this asks once per launch and keeps the file encrypted.

Windows
  - The same file and the same rules. The encryption is Windows' own (DPAPI): the secrets can
    only be opened by your Windows account on this PC, and the file is also tied to this PC's
    machine ID like on the Mac.
  - "Touch ID" is Windows Hello (fingerprint, face or PIN). If Hello isn't set up on this PC
    there is nothing to ask with, and she doesn't ask.

Old Keychain items are read once (the Keychain may ask one last time) and moved in here.
They're left in the Keychain untouched; delete them in Keychain Access if you like
(ParcelWidget-Gmail, ParcelWidget-ImageAPI).
"""
import base64
import ctypes
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time

import instance
from plat import HIDE, IS_MAC, IS_WIN, lock_file, powershell

PATH = os.path.join(instance.BASE, "secrets.vault")
CAN_ASK = IS_MAC or IS_WIN    # Touch ID / Windows Hello
ASK = True                # ask for Touch ID before the first use (Settings → General)
LANG = "en"
RETRY_AFTER = 30 * 60     # after a cancelled Touch ID, background jobs wait this long before asking again
REASON = {"en": "unlock Parcel Widget's saved passwords", "zh": "解锁快递小组件保存的密码"}

_lock = threading.Lock()          # one Touch ID dialog at a time
_unlocked = False
_declined_at = 0.0
_key = None
_cache = None                     # name -> secret, once unlocked


class Locked(Exception):
    """Touch ID was cancelled or failed; str() says why"""


# ---------------- crypto ----------------
def _machine_id():
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except Exception:
            return "no-hardware-id"
    try:
        out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True,
                             timeout=10).stdout.decode()
        m = re.search(r'"IOPlatformUUID" = "([^"]+)"', out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "no-hardware-id"


def _keys(salt):
    global _key
    if _key is None or _key[0] != salt:
        k = hashlib.pbkdf2_hmac("sha256", ("ParcelWidget vault|" + _machine_id()).encode(), salt, 200000, 64)
        _key = (salt, k[:32], k[32:])
    return _key[1], _key[2]


_cc = None


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(op, key, iv, data):
    """Windows: encrypt (op 0) / decrypt (op 1) with the data protection API - only this Windows
    account on this PC can open it. key + iv go in as extra entropy, so the file is tied to
    this PC's machine ID as well."""
    crypt32, kernel32 = ctypes.WinDLL("crypt32", use_last_error=True), ctypes.WinDLL("kernel32")
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return _Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf
    src, _k1 = blob(data)
    ent, _k2 = blob(key + iv)
    out = _Blob()
    fn = crypt32.CryptUnprotectData if op else crypt32.CryptProtectData
    # (in, description, entropy, reserved, prompt, flags: CRYPTPROTECT_UI_FORBIDDEN, out)
    if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out)):
        raise ValueError("Windows data protection error %d" % ctypes.get_last_error())
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def _aes(op, key, iv, data):
    """AES-256-CBC with PKCS7 padding via CommonCrypto (part of macOS); on Windows, DPAPI"""
    global _cc
    if IS_WIN:
        return _dpapi(op, key, iv, data)
    if _cc is None:
        _cc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        _cc.CCCrypt.restype = ctypes.c_int32
    out = ctypes.create_string_buffer(len(data) + 32)
    moved = ctypes.c_size_t(0)
    rc = _cc.CCCrypt(ctypes.c_uint32(op), ctypes.c_uint32(0), ctypes.c_uint32(1),   # AES, PKCS7
                     key, ctypes.c_size_t(len(key)), iv, data, ctypes.c_size_t(len(data)),
                     out, ctypes.c_size_t(len(out)), ctypes.byref(moved))
    if rc != 0:
        raise ValueError("CommonCrypto error %d" % rc)
    return out.raw[:moved.value]


def _seal(payload, salt):
    ek, mk = _keys(salt)
    iv = secrets.token_bytes(16)
    ct = _aes(0, ek, iv, json.dumps(payload).encode())
    mac = hmac.new(mk, salt + iv + ct, hashlib.sha256).digest()
    b = lambda x: base64.b64encode(x).decode()   # noqa: E731
    return {"v": 1, "salt": b(salt), "iv": b(iv), "ct": b(ct), "mac": b(mac), "names": sorted(payload)}


def _open(doc):
    d = lambda k: base64.b64decode(doc[k])       # noqa: E731
    salt, iv, ct = d("salt"), d("iv"), d("ct")
    ek, mk = _keys(salt)
    if not hmac.compare_digest(hmac.new(mk, salt + iv + ct, hashlib.sha256).digest(), d("mac")):
        raise ValueError("the vault was made on another computer, or is damaged")
    return json.loads(_aes(1, ek, iv, ct))


def _read_doc():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _write(payload):
    """save (other copies of the widget may write too: under a file lock, atomically)"""
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    doc = _read_doc()
    salt = base64.b64decode(doc["salt"]) if doc else secrets.token_bytes(16)
    tmp = PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(_seal(payload, salt), f)
    os.replace(tmp, PATH)


def _update(fn):
    """read-modify-write the secrets under a lock shared by all copies"""
    global _cache
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH + ".lock", "ab") as lk:
        lock_file(lk, wait=15)       # closing the file lets go of it
        doc = _read_doc()
        payload = _open(doc) if doc else {}
        fn(payload)
        _write(payload)
        if _cache is not None:
            _cache = dict(payload)


# ---------------- Touch ID ----------------
# Windows Hello, asked through Windows PowerShell (it can talk to the Windows Runtime; nothing to install)
_HELLO_PS = r'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Security.Credentials.UI.UserConsentVerifier,Windows.Security.Credentials.UI,ContentType=WindowsRuntime] | Out-Null
$a = Await ([Windows.Security.Credentials.UI.UserConsentVerifier]::CheckAvailabilityAsync()) ([Windows.Security.Credentials.UI.UserConsentVerifierAvailability])
if ("$a" -ne 'Available') { Write-Output "unavailable:$a"; exit 0 }
$r = Await ([Windows.Security.Credentials.UI.UserConsentVerifier]::RequestVerificationAsync($env:PW_ARG0)) ([Windows.Security.Credentials.UI.UserConsentVerificationResult])
Write-Output "result:$r"
'''


def _hello(reason):
    """Windows Hello: (confirmed, why not). Not set up on this PC -> nothing to ask with -> confirmed."""
    code, out, err = powershell(_HELLO_PS, [reason], timeout=200)
    out = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if out == "result:Verified":
        return True, ""
    if out.startswith("unavailable:") or out in ("result:DeviceNotPresent", "result:NotConfiguredForUser",
                                                  "result:DisabledByPolicy"):
        return True, ""
    if out.startswith("result:"):
        return False, out[7:]            # Canceled, RetriesExhausted, DeviceBusy
    # PowerShell itself failed (a Windows without the Windows Runtime, a locked-down PC): the file
    # is still encrypted for this Windows account, so don't lock the owner out of their own secrets
    from core import log
    log("vault: Windows Hello couldn't be asked (%s)" % (err or "exit %s" % code)[:160])
    return True, ""


def _touch_id(reason):
    """True if the owner confirmed (Touch ID, or the Mac's password as fallback)"""
    if IS_WIN:
        return _hello(reason)
    import LocalAuthentication as LA
    ctx = LA.LAContext.alloc().init()
    ok, _ = ctx.canEvaluatePolicy_error_(LA.LAPolicyDeviceOwnerAuthentication, None)
    if not ok:
        return True, ""          # no Touch ID and no password set up: nothing to ask with
    done, res = threading.Event(), {}

    def reply(success, error):
        res["ok"], res["err"] = bool(success), (error.localizedDescription() if error else "")
        done.set()
    ctx.evaluatePolicy_localizedReason_reply_(LA.LAPolicyDeviceOwnerAuthentication, reason, reply)
    if not done.wait(180):
        ctx.invalidate()
        return False, "timed out"
    return res["ok"], res.get("err", "")


def unlock(force=False):
    """make the secrets readable for this launch; raises Locked. force: ask even right after a
    cancel (the user asked for it, e.g. "Try again")"""
    global _unlocked, _declined_at
    if _unlocked or not ASK or not CAN_ASK:
        _unlocked = _unlocked or not ASK or not CAN_ASK
        return
    with _lock:
        if _unlocked:
            return
        if not force and time.time() - _declined_at < RETRY_AFTER:
            raise Locked("cancelled")
        from core import log
        log("vault: asking for %s" % ("Windows Hello" if IS_WIN else "Touch ID"))
        ok, err = _touch_id(REASON.get(LANG, REASON["en"]))
        if not ok:
            _declined_at = time.time()
            log("vault: still locked (%s)" % (err or "cancelled"))
            raise Locked("cancelled")
        _unlocked, _declined_at = True, 0.0
        log("vault: unlocked")


def is_unlocked():
    return _unlocked or not ASK


def lock():
    global _unlocked, _cache
    _unlocked, _cache = False, None


# ---------------- the secrets ----------------
_in_keychain = {}


def has(name, keychain=None):
    """is something saved under this name? (never asks)"""
    doc = _read_doc()
    if doc and name in doc.get("names", []):
        return True
    if keychain and IS_MAC:     # not moved in yet: the Keychain item's attributes (not its secret)
        if keychain not in _in_keychain:
            try:
                r = subprocess.run(["security", "find-generic-password", "-s", keychain[0], "-a", keychain[1]],
                                   capture_output=True, timeout=10, **HIDE)
                _in_keychain[keychain] = r.returncode == 0
            except Exception:
                _in_keychain[keychain] = False
        return _in_keychain[keychain]
    return False


def get(name, keychain=None, force=False):
    """the secret (or ""); asks for Touch ID first if needed (raises Locked).
    keychain: (service, account) of an old Keychain item to move in when it isn't here yet."""
    global _cache
    if not has(name, keychain):
        return ""
    unlock(force)
    if _cache is None:
        doc = _read_doc()
        _cache = _open(doc) if doc else {}
    if name in _cache:
        return _cache[name]
    if keychain:
        try:
            import keyring
            v = keyring.get_password(*keychain) or ""
        except Exception:
            v = ""
        if v:
            set(name, v)
            from core import log
            log("vault: moved %s in from the Keychain" % name.split(":")[0])
        return v
    return ""


def set(name, value):    # noqa: A001 - vault.set / vault.get
    def f(p):
        if value:
            p[name] = value
        else:
            p.pop(name, None)
    _update(f)


def delete(name):
    set(name, "")
