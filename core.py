"""Shared bits: paths, config, log, Keychain, skins, size presets. No UI, no platform code."""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

if IS_WIN:
    APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ParcelWidget")
else:
    APP_DIR = os.path.expanduser("~/Library/Application Support/ParcelWidget")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "widget.log")
FROZEN = bool(getattr(sys, "frozen", False))   # running from the packaged .app (PyInstaller)
if FROZEN:
    HERE = getattr(sys, "_MEIPASS", HERE)


def _ui_dir():
    """The pages and skins. In the packaged app the bundle is read-only, so the pages are
    copied to the app data folder at each launch; custom skins are made there too."""
    src = os.path.join(HERE, "ui")
    if not FROZEN:
        return src
    import shutil
    dst = os.path.join(APP_DIR, "ui")
    os.makedirs(os.path.join(dst, "skins"), exist_ok=True)
    for name in os.listdir(src):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if name == "skins":
            for sk in os.listdir(s):    # bundled skins are refreshed, custom ones are kept
                if os.path.isdir(os.path.join(s, sk)):
                    shutil.rmtree(os.path.join(d, sk), ignore_errors=True)
                    shutil.copytree(os.path.join(s, sk), os.path.join(d, sk))
        elif os.path.isfile(s):
            shutil.copy2(s, d)
    return dst


UI_DIR = _ui_dir()
SKINS_DIR = os.path.join(UI_DIR, "skins")
KEYRING_SERVICE = "ParcelWidget-Gmail"

DEFAULT_CONFIG = {
    "lang": "en",
    "always_on_top": False,
    "size_preset": "14",
    "skin": "whale-maid",    # folder name under ui/skins
    "skin_side": "right",    # which side of the screen corner she stands on (balloon opens the other way)
    "parcels": {
        "gmail_address": "",
        "scan_days": 14,
        "headless": True,    # run the tracking browser invisibly
        "browser": "chrome",
        # automatic checks: every `every_min` minutes from `start` to `end` (local time)
        "start": "09:00",
        "end": "19:00",
        "every_min": 90,
    },
    "sysmon": {
        "period": 10,        # seconds per candle
        "colors": "auto",    # "auto" (by language), "green_up" (US) or "red_up" (China)
    },
}

# character height and balloon size per screen size (balloon w/h in px, zoom for the UI)
SIZE_PRESETS = {
    "13": {"label": '13"', "w": 248, "h": 360, "zoom": 0.74},
    "14": {"label": '14"', "w": 262, "h": 390, "zoom": 0.78},
    "15": {"label": '15"', "w": 276, "h": 420, "zoom": 0.82},
    "16": {"label": '16"', "w": 292, "h": 450, "zoom": 0.87},
    "ext": {"label": "External", "w": 320, "h": 500, "zoom": 0.95},
}


def preset(cfg):
    return SIZE_PRESETS.get(str(cfg.get("size_preset")), SIZE_PRESETS["14"])


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg)
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def trim_log(keep=512 * 1024, limit=2 * 1024 * 1024):
    """keep widget.log from growing forever: past `limit` bytes, keep the last `keep`"""
    try:
        if os.path.getsize(LOG_PATH) > limit:
            with open(LOG_PATH, "rb") as f:
                f.seek(-keep, 2)
                tail = f.read()
            tail = tail[tail.find(b"\n") + 1:]
            with open(LOG_PATH, "wb") as f:
                f.write(tail)
    except OSError:
        pass


# keys that used to live at the top level of config.json (before features had their own section)
_OLD_PARCEL_KEYS = ("gmail_address", "scan_days", "headless", "browser")


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            for k in _OLD_PARCEL_KEYS:
                if k in saved and "parcels" not in saved:
                    cfg["parcels"][k] = saved[k]
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                elif k not in _OLD_PARCEL_KEYS and k not in ("interval_minutes", "chat_collapsed"):
                    cfg[k] = v
        except Exception:
            pass
    return cfg


_cfg_lock = threading.Lock()


def save_config(cfg):
    with _cfg_lock:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)


MEMORY_PATH = os.path.join(APP_DIR, "memory.json")
_mem_lock = threading.Lock()


def load_memory(key):
    """What a feature remembered from its last run, e.g. {"ts": ..., "data": ...} (or {})."""
    with _mem_lock:
        try:
            with open(MEMORY_PATH, encoding="utf-8") as f:
                return json.load(f).get(key) or {}
        except Exception:
            return {}


def save_memory(key, value):
    with _mem_lock:
        try:
            with open(MEMORY_PATH, encoding="utf-8") as f:
                mem = json.load(f)
        except Exception:
            mem = {}
        mem[key] = value
        tmp = MEMORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False)
        os.replace(tmp, MEMORY_PATH)


def get_password(address):
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, address) or ""
    except Exception:
        return ""


def set_password(address, pw):
    import keyring  # macOS Keychain / Windows Credential Manager, never a plain file
    keyring.set_password(KEYRING_SERVICE, address, pw)


def later(fn, delay=0.05):
    """Run fn on another thread shortly. Window calls made directly inside a js_api
    callback can deadlock on macOS, because pywebview still has to send the return
    value back to the page."""
    def run():
        time.sleep(delay)
        try:
            fn()
        except Exception as ex:
            log("window op error %r" % ex)
    threading.Thread(target=run, daemon=True).start()


def list_skins():
    """Every folder in ui/skins that has a skin.json is a skin."""
    out = []
    if os.path.isdir(SKINS_DIR):
        for d in sorted(os.listdir(SKINS_DIR)):
            p = os.path.join(SKINS_DIR, d, "skin.json")
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        m = json.load(f)
                    m["id"] = d
                    out.append(m)
                except Exception as e:
                    log("bad skin %s: %r" % (d, e))
    return out
