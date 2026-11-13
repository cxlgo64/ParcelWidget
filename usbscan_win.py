"""Windows: what's plugged in over USB and which driver runs each device.
The Windows side of usbscan.py (same scan() result, see there).

Everything comes from the registry, where Windows keeps every USB device it has ever seen
(HKLM\\SYSTEM\\CurrentControlSet\\Enum\\USB) and the driver installed for each
(...\\Control\\Class\\{class}\\NNNN); the configuration manager says which of them are plugged
in right now. No administrator rights, no helper programs: a scan takes a few milliseconds.

A device with several functions (a keyboard with a trackpad, a headset with buttons) shows up
as one "composite" device plus one entry per function (…&MI_00, …&MI_01); like on the Mac, the
device's drivers are those of its functions, or its own when it has only one.

    drivers      [{bundle, name, version, date, provider, apple, type: "inf", path}]
                 apple: the driver comes with Windows (provider Microsoft); it only gets newer
                 with Windows Update
"""
import ctypes
import os
import re

KIND = {1: "audio", 2: "network", 3: "input", 6: "camera", 7: "printer", 8: "storage", 9: "hub",
        10: "network", 14: "video", 0x10: "video", 0x11: "billboard", 0xE0: "wireless", 0xFF: "vendor"}
KIND_ORDER = ["printer", "storage", "network", "camera", "video", "audio", "input", "wireless", "hub",
              "billboard", "vendor"]
# when the USB class says nothing (0xFF "vendor specific"), Windows' own device class does
WIN_CLASS = {"printer": "printer", "usbprint": "printer", "hidclass": "input", "keyboard": "input", "mouse": "input",
             "net": "network", "bluetooth": "wireless", "media": "audio", "audioendpoint": "audio",
             "image": "camera", "camera": "camera", "diskdrive": "storage", "wpd": "storage", "scsiadapter": "storage",
             "smartcardreader": "vendor", "ports": "vendor", "modem": "network", "biometric": "input",
             "monitor": "video", "display": "video"}
SERVICE_KIND = {"usbstor": "storage", "uaspstor": "storage", "usbprint": "printer", "usbhub": "hub", "usbhub3": "hub",
                "bthusb": "wireless", "usbaudio": "audio", "usbaudio2": "audio", "usbvideo": "camera",
                "hidusb": "input", "usbccid": "vendor", "wudfwpdmtp": "storage"}
GENERIC_NAMES = re.compile(r"^(usb |generic |unknown |composite )|\b(composite device|input device|mass storage device|"
                           r"printing support|root hub|generic usb hub|usb hub)\b", re.I)
ENUM = r"SYSTEM\CurrentControlSet\Enum"
CLASSES = r"SYSTEM\CurrentControlSet\Control\Class"

_cfg = None


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


class _PropKey(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", ctypes.c_uint32)]


# DEVPKEY_Device_BusReportedDeviceDesc: the name the device itself reports ("Logitech G502")
_BUS_DESC = _PropKey(_GUID(0x540B947E, 0x8B40, 0x45BC, (ctypes.c_ubyte * 8)(0xA2, 0xA8, 0x6A, 0x0B, 0x89, 0x4C, 0xBD, 0xA2)), 4)


def _cm():
    global _cfg
    if _cfg is None:
        c = ctypes.WinDLL("cfgmgr32")
        c.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p, ctypes.c_uint32]
        c.CM_Get_DevNode_PropertyW.argtypes = [ctypes.c_uint32, ctypes.POINTER(_PropKey), ctypes.POINTER(ctypes.c_uint32),
                                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint32]
        _cfg = c
    return _cfg


def _node(instance_id):
    """the device node of a device that is plugged in now, or None"""
    n = ctypes.c_uint32()
    return n.value if _cm().CM_Locate_DevNodeW(ctypes.byref(n), instance_id, 0) == 0 else None


def _bus_name(node):
    try:
        buf = ctypes.create_unicode_buffer(256)
        typ, size = ctypes.c_uint32(), ctypes.c_uint32(ctypes.sizeof(buf))
        if _cm().CM_Get_DevNode_PropertyW(node, ctypes.byref(_BUS_DESC), ctypes.byref(typ), buf, ctypes.byref(size), 0) == 0:
            return buf.value.strip()
    except Exception:
        pass
    return ""


def _values(key):
    """all values of an open registry key: {name: value}"""
    import winreg
    out, i = {}, 0
    while True:
        try:
            name, val, _ = winreg.EnumValue(key, i)
        except OSError:
            return out
        out[name] = val
        i += 1


def _subkeys(root, path):
    import winreg
    try:
        with winreg.OpenKey(root, path) as k:
            i = 0
            while True:
                try:
                    yield winreg.EnumKey(k, i)
                except OSError:
                    return
                i += 1
    except OSError:
        return


def _read(path):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            return _values(k)
    except OSError:
        return {}


def _text(v):
    """'@oem12.inf,%name%;Real Name' -> 'Real Name'"""
    s = str(v or "")
    return s.rsplit(";", 1)[-1].strip() if s.startswith("@") else s.strip()


def _list(v):
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else ([str(v)] if v else [])


_drv_cache = {}


def _driver(vals):
    """the driver installed for a device entry, or None (nothing drives it)"""
    ref = str(vals.get("Driver") or "")
    service = str(vals.get("Service") or "")
    if not ref and not service:
        return None
    if ref not in _drv_cache:
        _drv_cache[ref] = _read(CLASSES + "\\" + ref) if ref else {}
    d = _drv_cache[ref]
    inf = str(d.get("InfPath") or "")
    provider = _text(d.get("ProviderName"))
    name = _text(d.get("DriverDesc")) or service or inf
    path = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "INF", inf) if inf else ""
    return {"bundle": "%s (%s)" % (service or name, inf) if inf else (service or name), "name": name,
            "version": str(d.get("DriverVersion") or "") or None, "date": str(d.get("DriverDate") or ""),
            "provider": provider, "apple": provider.lower() in ("microsoft", "microsoft corporation", ""),
            "type": "inf", "path": path}


def _classes(vals):
    """USB class numbers named in a device entry's compatible IDs, and whether it's IPP over USB"""
    out, ipp = set(), False
    for cid in _list(vals.get("CompatibleIDs")):
        m = re.match(r"USB\\(?:Dev)?Class_([0-9A-F]{2})(?:&SubClass_([0-9A-F]{2})(?:&Prot_([0-9A-F]{2}))?)?", cid, re.I)
        if not m:
            continue
        c = int(m.group(1), 16)
        if c:
            out.add(c)
        if (c, m.group(2), m.group(3)) == (7, "01", "04"):
            ipp = True
    return out, ipp


def _win_kind(vals):
    k = SERVICE_KIND.get(str(vals.get("Service") or "").lower())
    if k:
        return k
    cls = str(vals.get("Class") or "").lower()
    if not cls and vals.get("ClassGUID"):
        cls = str(_read(CLASSES + "\\" + str(vals["ClassGUID"])).get("Class") or "").lower()
    return WIN_CLASS.get(cls)


def scan():
    import winreg
    root = winreg.HKEY_LOCAL_MACHINE
    _drv_cache.clear()
    present = {}        # "VID_xxxx&PID_yyyy[&MI_zz]" -> [(instance, values, node)]
    for hw in _subkeys(root, ENUM + r"\USB"):
        if not re.match(r"VID_[0-9A-F]{4}&PID_[0-9A-F]{4}", hw, re.I):
            continue        # root hubs and the like
        for inst in list(_subkeys(root, "%s\\USB\\%s" % (ENUM, hw))):
            node = _node("USB\\%s\\%s" % (hw, inst))
            if node is None:
                continue    # seen before, not plugged in now
            present.setdefault(hw.upper(), []).append((inst, _read("%s\\USB\\%s\\%s" % (ENUM, hw, inst)), node))

    devices = []
    for hw, entries in sorted(present.items()):
        if "&MI_" in hw:
            continue
        vid, pid = hw[4:8].lower(), hw[13:17].lower()
        for inst, vals, node in entries:
            # this device's functions: entries named ...&MI_nn whose instance starts with its prefix
            prefix = str(vals.get("ParentIdPrefix") or "").upper()
            kids = [(i, v) for h, es in present.items() if h.startswith(hw + "&MI_")
                    for i, v, _ in es if not prefix or i.upper().startswith(prefix)]
            classes, ipp = _classes(vals)
            kinds = {_win_kind(vals)}
            drivers, seen = [], set()
            for _, kv in kids:
                c, i = _classes(kv)
                classes |= c
                ipp = ipp or i
                kinds.add(_win_kind(kv))
            for v in ([kv for _, kv in kids] or [vals]):
                d = _driver(v)
                if d and d["bundle"] not in seen:
                    seen.add(d["bundle"])
                    drivers.append(d)
            kinds |= {KIND.get(c, "other") for c in classes}
            kinds.discard(None)
            if len(kinds) > 1:
                kinds.discard("vendor")
                kinds.discard("other")
            kind = next((k for k in KIND_ORDER if k in kinds), "other")
            bus = _bus_name(node)
            desc = _text(vals.get("FriendlyName")) or _text(vals.get("DeviceDesc"))
            name = bus or desc or "USB device"
            mfg = _text(vals.get("Mfg"))
            if mfg.startswith("(") or mfg.lower() in ("microsoft", "generic"):
                mfg = ""        # "(Standard system devices)": Windows' generic driver, not the maker
            devices.append({
                "key": "%s:%s@%s" % (vid, pid, inst.lower()), "vid": vid, "pid": pid,
                "location": _text(vals.get("LocationInformation")),
                "name": name, "vendor": mfg, "generic_name": bool(GENERIC_NAMES.search(name)),
                "serial": inst if "&" not in inst else "",      # a real serial number has no "&" in it
                "speed": "", "kind": kind, "classes": sorted(classes), "drivers": drivers, "ipp_usb": ipp,
            })
    return devices
