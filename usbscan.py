"""macOS: what's plugged in over USB, which driver runs each device, and the printers.

Everything here is local and quick (ioreg / kmutil / lpstat take well under a second);
looking things up online is in driverinfo.py.

scan() -> [device], each:
    key          "vid:pid@location", stable while it stays in the same port
    name, vendor, vid, pid ("0bda"), serial, speed ("5 Gb/s"), location ("0x02214000")
    kind         hub | printer | storage | network | input | audio | video | camera | wireless |
                 billboard | vendor | other
    classes      USB interface classes, e.g. [2, 10]
    ipp_usb      a printer that speaks IPP over USB (AirPrint: macOS needs no driver for it)
    drivers      [{bundle, name, version, apple, type: kext|dext, path}]   the device's own drivers
"""
import glob
import os
import plistlib
import re
import subprocess
import urllib.parse

KIND = {1: "audio", 2: "network", 3: "input", 6: "camera", 7: "printer", 8: "storage", 9: "hub",
        10: "network", 14: "video", 0x10: "video", 0x11: "billboard", 0xE0: "wireless", 0xFF: "vendor"}
# a device's kind = its most telling interface
KIND_ORDER = ["printer", "storage", "network", "camera", "video", "audio", "input", "wireless", "hub",
              "billboard", "vendor"]
SPEED = {0: "1.5 Mb/s", 1: "12 Mb/s", 2: "480 Mb/s", 3: "5 Gb/s", 4: "10 Gb/s", 5: "20 Gb/s"}
GENERIC = ("generic", "", None)


def _run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).stdout
    except Exception:
        return b""


def _drivers_of(dev):
    """The drivers attached to this device: those on its interfaces, else on the device itself.
    Deeper layers (network stacks, block storage, ...) and nested devices are not its drivers."""
    on_dev, on_if = [], []
    for c in dev.get("IORegistryEntryChildren", []):
        cls = c.get("IOObjectClass", "")
        if cls == "IOUSBHostDevice" or "UserClient" in cls:
            continue
        if cls == "IOUSBHostInterface":
            for d in c.get("IORegistryEntryChildren", []):
                if d.get("CFBundleIdentifier") and "UserClient" not in d.get("IOObjectClass", ""):
                    on_if.append(d)
        elif c.get("CFBundleIdentifier"):
            on_dev.append(c)
    out, seen = [], set()
    for d in (on_if or on_dev):
        b = d["CFBundleIdentifier"]
        if b in seen:
            continue
        seen.add(b)
        out.append({"bundle": b, "name": b.rsplit(".", 1)[-1],
                    "type": "dext" if d.get("IOUserServerName") else "kext", "apple": b.startswith("com.apple.")})
    # the generic "composite device" driver only matters if nothing else runs the device
    if len(out) > 1:
        out = [d for d in out if d["bundle"] != "com.apple.driver.usb.AppleUSBHostCompositeDevice"] or out
    return out


def _interfaces(dev):
    return [c for c in dev.get("IORegistryEntryChildren", []) if c.get("IOObjectClass") == "IOUSBHostInterface"]


def _loaded_versions():
    """bundle id -> version of the loaded kexts and the system / driver extensions"""
    v = {}
    for m in re.finditer(rb"\s([\w.\-]+) \(([^)]+)\) [0-9A-F-]{36}", _run(["kmutil", "showloaded", "--list-only"])):
        v[m.group(1).decode()] = m.group(2).decode()
    for m in re.finditer(rb"\s([\w.\-]+) \(([^/)]+)(?:/[^)]*)?\)", _run(["systemextensionsctl", "list"])):
        v.setdefault(m.group(1).decode(), m.group(2).decode())
    return v


def _bundle_info(bundle, typ):
    """(version, path) of a driver bundle from its Info.plist on disk"""
    pats = (["/System/Library/DriverExtensions/*.dext", "/Library/DriverExtensions/*.dext",
             "/Library/SystemExtensions/*/*.dext", "/Applications/*.app/Contents/Library/SystemExtensions/*.dext"]
            if typ == "dext" else
            ["/Library/Extensions/*.kext", "/System/Library/Extensions/*.kext",
             "/System/Library/Extensions/*.kext/Contents/PlugIns/*.kext"])
    short = bundle.rsplit(".", 1)[-1].lower()
    cands = []
    for p in pats:
        cands += glob.glob(p)
    # likely names first: a full scan of /System/Library/Extensions reads hundreds of plists
    cands.sort(key=lambda p: short not in os.path.basename(p).lower())
    for path in cands[:400]:
        for ip in (os.path.join(path, "Contents", "Info.plist"), os.path.join(path, "Info.plist")):
            try:
                with open(ip, "rb") as f:
                    info = plistlib.load(f)
            except Exception:
                continue
            if info.get("CFBundleIdentifier") == bundle:
                return info.get("CFBundleShortVersionString") or info.get("CFBundleVersion"), path
    return None, None


_info_cache = {}


def scan():
    raw = _run(["ioreg", "-a", "-r", "-c", "IOUSBHostDevice", "-l"])
    try:
        roots = plistlib.loads(raw) if raw.strip() else []
    except Exception:
        roots = []
    nodes = []

    def find(n):
        if n.get("IOObjectClass") == "IOUSBHostDevice":
            nodes.append(n)
        for c in n.get("IORegistryEntryChildren", []):
            find(c)
    for r in roots:
        find(r)

    versions = None
    devices, seen = [], set()
    for n in nodes:
        loc = n.get("locationID", 0)
        vid, pid = n.get("idVendor", 0), n.get("idProduct", 0)
        key = "%04x:%04x@%08x" % (vid, pid, loc)
        if key in seen:
            continue
        seen.add(key)
        ifs = _interfaces(n)
        classes = sorted({i.get("bInterfaceClass") for i in ifs if i.get("bInterfaceClass") is not None})
        if n.get("bDeviceClass") == 9:
            classes = sorted(set(classes) | {9})
        kinds = {KIND.get(c, "other") for c in classes}
        kind = next((k for k in KIND_ORDER if k in kinds), "other")
        drivers = _drivers_of(n)
        for d in drivers:
            if d["bundle"] not in _info_cache:
                if versions is None:
                    versions = _loaded_versions()
                ver = versions.get(d["bundle"])
                path = None
                if not ver or not d["apple"]:
                    ver2, path = _bundle_info(d["bundle"], d["type"])
                    ver = ver or ver2
                _info_cache[d["bundle"]] = (ver, path)
            d["version"], d["path"] = _info_cache[d["bundle"]]
        serial = n.get("kUSBSerialNumberString") or n.get("USB Serial Number") or ""
        devices.append({
            "key": key, "vid": "%04x" % vid, "pid": "%04x" % pid, "location": "0x%08x" % loc,
            "name": n.get("kUSBProductString") or n.get("USB Product Name") or n.get("IORegistryEntryName") or "USB device",
            "vendor": n.get("kUSBVendorString") or n.get("USB Vendor Name") or "",
            "serial": "" if serial.lower() in ("not provided", "0") else serial,
            "speed": SPEED.get(n.get("Device Speed"), ""),
            "kind": kind, "classes": classes, "drivers": drivers,
            "ipp_usb": any(i.get("bInterfaceClass") == 7 and i.get("bInterfaceSubClass") == 1
                           and i.get("bInterfaceProtocol") == 4 for i in ifs),
        })
    return devices


# ---------------- printers ----------------
def configured_printers():
    """[(queue name, device uri)] of the printers in System Settings → Printers & Scanners"""
    out = []
    for line in _run(["lpstat", "-v"]).decode("utf-8", "replace").splitlines():
        m = re.match(r"device for (.+?): (.+)$", line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", urllib.parse.unquote(str(s or "")).lower())


def is_configured(dev, printers=None):
    """is this USB printer already in the printer list? (matched by serial number or model name)"""
    printers = configured_printers() if printers is None else printers
    serial, name = _norm(dev.get("serial")), _norm(dev.get("name"))
    for q, uri in printers:
        if not (uri.startswith("usb:") or uri.startswith("ippusb:") or uri.startswith("dnssd:")):
            continue
        u = _norm(uri)
        if (serial and len(serial) >= 4 and serial in u) or (name and len(name) >= 5 and name in u):
            return q
    return None


def device_id(dev):
    """IEEE 1284 device id of a USB printer as CUPS sees it ({"MFG", "MDL", ...}), or {}"""
    raw = _run(["lpinfo", "-l", "-v", "--include-schemes", "usb"], timeout=40).decode("utf-8", "replace")
    serial, name = _norm(dev.get("serial")), _norm(dev.get("name"))
    for block in re.split(r"\n(?=Device: )", raw):
        if not block.startswith("Device: "):
            continue
        uri = re.search(r"uri = (\S+)", block)
        did = re.search(r"device-id = (.*)", block)
        u = _norm(uri.group(1) if uri else "")
        if did and ((serial and serial in u) or (name and name in u)):
            out = {}
            for part in did.group(1).split(";"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    out[k.strip().upper()] = v.strip()
            out.setdefault("MFG", out.get("MANUFACTURER", ""))
            out.setdefault("MDL", out.get("MODEL", ""))
            return out
    return {}


def local_driver(make, model):
    """a printer driver (PPD) for this model already on the Mac, or None"""
    raw = _run(["lpinfo", "-m", "--make-and-model", ("%s %s" % (make, model)).strip()], timeout=40)
    want = _norm(model)
    for line in raw.decode("utf-8", "replace").splitlines():
        ppd, _, desc = line.partition(" ")
        if want and want in _norm(desc) and "everywhere" not in ppd and "airprint" not in ppd.lower():
            return {"ppd": ppd, "name": desc.strip()}
    return None
