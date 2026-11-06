"""macOS: printers in the printer list, grouped by the physical printer, and one-click AirPrint.

AirPrint printers need no driver: macOS asks the printer what it can do and builds the
printer entry from that. This module
  - groups the printer list (lpstat) by physical printer - the same printer is often in the list
    two or three times (USB + IPP-over-USB, or the same IP address added twice), usually with one
    good AirPrint entry and others using a generic driver or gone offline;
  - sets a printer up with AirPrint in one go:
        network printer   lpadmin -m everywhere on its ipp(s):// address (after asking the printer
                          whether it speaks AirPrint: image/urf or image/pwg-raster)
        USB printer       the AirPrint description macOS already made for that model, on its usb://
                          address (macOS runs it over IPP-over-USB itself); if there's none yet, the
                          macOS "Add Printer" window opens, where AirPrint is picked in "Use"
  - removes the duplicates of a printer, keeping the best entry, and makes an entry the default.

groups(usb_devices) -> [group], each:
    key, name, via: usb|network|bonjour, connected (USB: plugged in), uri (where to set it up),
    queues [{name, uri, desc, model, airprint, offline, default, ppd}], best (queue name or None),
    status: ready (an AirPrint entry works) | other (only entries with another driver) |
            offline (only entries that don't answer) | none (not in the printer list)
"""
import os
import re
import shlex
import subprocess
import urllib.parse

PPD_DIR = "/etc/cups/ppd"
ADD_PRINTER = "/System/Library/CoreServices/AddPrinter.app"
AIRPRINT_FORMATS = ("image/urf", "image/pwg-raster")
GENERIC_PATHS = ("", "/", "/ipp", "/ipp/print", "/ipp/printer", "/printers/print")


class SetupError(Exception):
    """a step failed; str() is short enough to show"""


def _run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except Exception as e:
        return 1, "", str(e)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", urllib.parse.unquote(str(s or "")).lower())


# ---------------- the printer list ----------------
def _ppd_info(queue):
    path = os.path.join(PPD_DIR, queue + ".ppd")
    info = {"ppd": path if os.path.exists(path) else None, "model": "", "nick": "", "airprint": False}
    try:
        with open(path, "rb") as f:
            head = f.read(200000).decode("latin-1", "replace")
    except Exception:
        return info
    for key in ("ModelName", "NickName"):
        m = re.search(r'^\*%s:\s*"([^"]*)"' % key, head, re.M)
        if m:
            info["model" if key == "ModelName" else "nick"] = m.group(1)
    info["airprint"] = bool(re.search(r"^\*APAirPrint:\s*True", head, re.M)
                            or re.search(r'^\*cupsFilter2?:\s*"image/(urf|pwg-raster)', head, re.M)
                            or "IPP Everywhere" in info["nick"])
    return info


def queues():
    """[{name, uri, desc, model, airprint, offline, default, ppd}] of the printer list"""
    _, out, _ = _run(["lpstat", "-v"])
    qs = []
    for line in out.splitlines():
        m = re.match(r"device for (.+?): (.+)$", line.strip())
        if m:
            qs.append({"name": m.group(1), "uri": m.group(2)})
    _, out, _ = _run(["lpstat", "-l", "-p"])
    detail, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"printer (\S+) ", line)
        if m:
            cur = detail.setdefault(m.group(1), {"desc": "", "alerts": "", "disabled": "disabled" in line})
            continue
        if cur is not None:
            m = re.match(r"\s+(Description|Alerts):\s*(.*)", line)
            if m:
                cur[m.group(1).lower() if m.group(1) == "Alerts" else "desc"] = m.group(2).strip()
    _, out, _ = _run(["lpstat", "-d"])
    m = re.search(r":\s*(\S+)\s*$", out.strip())
    default = m.group(1) if m else None
    for q in qs:
        d = detail.get(q["name"], {})
        info = _ppd_info(q["name"])
        q.update(desc=d.get("desc") or q["name"], model=info["model"] or info["nick"], nick=info["nick"],
                 airprint=info["airprint"], ppd=info["ppd"], default=q["name"] == default,
                 offline="offline" in d.get("alerts", "") or d.get("disabled", False))
    return qs


def _host_key(uri):
    """the physical printer a network address points at: its host, plus the path when that names
    one printer among many (a print server)"""
    u = urllib.parse.urlsplit(uri)
    host = (u.hostname or "").lower().rstrip(".")
    path = u.path.rstrip("/")
    return "net:" + host + ("" if path in GENERIC_PATHS or path.rstrip("/") in GENERIC_PATHS else path.lower())


def _usb_serial(uri):
    return (urllib.parse.parse_qs(urllib.parse.urlsplit(uri).query).get("serial") or [""])[0]


def usb_uris():
    """{serial or model: usb:// address} of the USB printers CUPS sees now"""
    _, out, _ = _run(["lpinfo", "-v", "--include-schemes", "usb"], timeout=40)
    res = {}
    for line in out.splitlines():
        m = re.match(r"\s*direct\s+(usb://\S+)", line)
        if m:
            uri = m.group(1)
            res[_norm(_usb_serial(uri)) or _norm(urllib.parse.urlsplit(uri).path)] = uri
    return res


def groups(usb_devices=(), qs=None, found=()):
    """the printer list grouped by physical printer (see the module doc). usb_devices: printers from
    usbscan.scan(); found: AirPrint printers found nearby (discover())"""
    qs = queues() if qs is None else qs
    out, by_key = [], {}

    def group(key, **kw):
        g = by_key.get(key)
        if not g:
            g = by_key[key] = dict({"key": key, "queues": [], "connected": False, "uri": None}, **kw)
            out.append(g)
        return g

    # plugged-in USB printers first
    usb = [d for d in usb_devices if d.get("kind") == "printer"]
    uris = {_norm(_usb_serial(q["uri"])): q["uri"] for q in qs if q["uri"].startswith("usb:") and _usb_serial(q["uri"])}
    if any(_norm(d.get("serial")) not in uris for d in usb):
        uris.update(usb_uris())
    for d in usb:
        s = _norm(d.get("serial"))
        group("usb:" + (s or _norm(d["name"])), name=d["name"], via="usb", connected=True,
              uri=uris.get(s) or uris.get(_norm("/" + d.get("vendor", "") + "/" + d["name"])), serial=s, model=d["name"])
    # plain usb:// entries before IPP-over-USB ones, which are tied to them by model
    for q in sorted(qs, key=lambda q: q["uri"].startswith("ippusb:")):
        uri = q["uri"]
        scheme = uri.split(":", 1)[0]
        if scheme == "usb":
            s = _norm(_usb_serial(uri))
            g = by_key.get("usb:" + s) if s else None
            g = g or next((x for x in out if x["via"] == "usb" and _norm(x.get("model")) == _norm(q["model"])
                           and not x.get("serial")), None)
            g = g or group("usb:" + (s or _norm(uri)), name=q["desc"], via="usb", serial=s, model=q["model"])
        elif scheme == "ippusb":
            # IPP over USB: tied to the USB printer of the same model
            g = next((x for x in out if x["via"] == "usb" and q["model"] and _norm(q["model"]) in
                      {_norm(x.get("model"))} | {_norm(y["model"]) for y in x["queues"]}), None)
            g = g or group("ippusb:" + _norm(uri), name=q["desc"], via="usb", model=q["model"])
        elif scheme in ("ipp", "ipps", "http", "https", "lpd", "socket", "dnssd", "mdns"):
            g = group(_host_key(uri), name=q["desc"], via="network", model=q["model"])
        else:
            g = group(scheme + ":" + _norm(uri), name=q["desc"], via="other", model=q["model"])
        g["queues"].append(q)
    for f in found:
        g = by_key.get(_host_key(f["uri"]))
        if not g:
            g = group(_host_key(f["uri"]), name=f["name"], via="bonjour", model=f.get("model", ""))
        g["uri"] = g.get("uri") or f["uri"]
        g["found"] = True
    for g in out:
        _rate(g)
    return out


def _rate(g):
    qs = g["queues"]
    if g["via"] == "network" and not g.get("uri"):
        g["uri"] = next((q["uri"] for q in qs if q["uri"].startswith(("ipps:", "ipp:"))), None) or \
            (qs and "ipp://%s/ipp/print" % urllib.parse.urlsplit(qs[0]["uri"]).hostname)
    if g["via"] == "usb" and g["connected"] is False and g.get("uri") is None:
        g["uri"] = next((q["uri"] for q in qs if q["uri"].startswith("usb:")), None)

    def score(q):
        # a working AirPrint entry; for USB the plain usb:// one (macOS does IPP-over-USB under it)
        return (q["airprint"] and not q["offline"], not q["offline"], q["airprint"],
                q["uri"].startswith("usb:") or q["uri"].startswith("ipps:"), q["default"])
    best = max(qs, key=score) if qs else None
    if best and best["airprint"] and not best["offline"]:
        g["status"], g["best"] = "ready", best["name"]
    elif best and not best["offline"]:
        g["status"], g["best"] = "other", None
    elif best:
        g["status"], g["best"] = "offline", None
    else:
        g["status"], g["best"] = "none", None
    g["extra"] = [q["name"] for q in qs if q["name"] != g["best"]] if g["best"] else []
    g["default"] = any(q["default"] for q in qs if q["name"] == g["best"])
    # a print server's queue (a path naming one printer among many) has its own sign-in: left alone
    g["server"] = g["via"] == "network" and len(g["key"].split("/", 1)) > 1
    g["can_setup"] = (g["via"] in ("network", "bonjour") and not g["server"]) or (g["via"] == "usb" and g["connected"])
    if not g["connected"] and g["via"] == "usb":
        # named after its AirPrint entry's model when there is one (the others may say "Generic ...")
        g["name"] = next((q["model"] for q in qs if q["airprint"] and q["model"]), None) or g.get("name")
    g["name"] = g.get("name") or g.get("model") or "Printer"


# ---------------- finding AirPrint printers ----------------
def discover(timeout=4):
    """AirPrint printers announced nearby (Bonjour): [{name, uri, model, uuid}]"""
    fmt = "{service_name}\t{service_uri}\t{txt_ty}\t{txt_UUID}\t{txt_URF}"
    _, out, _ = _run(["ippfind", "-T", str(timeout), "_ipps._tcp", "_ipp._tcp",
                      "-x", "echo", fmt, ";"], timeout=timeout + 10)
    res = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not parts[1]:
            continue
        name, uri, ty, uuid, urf = parts[:5]
        if not urf:     # not AirPrint
            continue
        key = uuid or name
        if key not in res or uri.startswith("ipps:"):
            res[key] = {"name": name, "uri": uri, "model": ty or name, "uuid": uuid}
    return list(res.values())


def probe(uri):
    """ask a network printer what it is: {model, info, uuid, airprint} or raise SetupError"""
    code, out, err = _run(["ipptool", "-T", "8", "-tv", uri, "get-printer-attributes.test"], timeout=30)
    if "successful-ok" not in out:
        lines = (err.strip() or out.strip()).splitlines()
        raise SetupError(lines[-1].strip()[:160] if lines else "no answer")
    attrs = {}
    for m in re.finditer(r"^\s+([\w-]+) \([^)]*\) = (.*)$", out, re.M):
        attrs.setdefault(m.group(1), m.group(2).strip())
    fmts = attrs.get("document-format-supported", "")
    return {"model": attrs.get("printer-make-and-model", ""), "info": attrs.get("printer-info", ""),
            "uuid": attrs.get("printer-uuid", ""),
            "airprint": any(f in fmts for f in AIRPRINT_FORMATS) or bool(attrs.get("urf-supported"))}


def address_uris(text):
    """what to try for an address the user typed: an ipp(s):// URL as is, else host -> the usual paths"""
    text = text.strip()
    if re.match(r"^ipps?://", text):
        return [text]
    host = re.sub(r"^\w+://", "", text).split("/")[0]
    if not re.match(r"^[A-Za-z0-9.\-:\[\]]+$", host or ""):
        raise SetupError("bad address")
    return ["ipps://%s/ipp/print" % host, "ipp://%s/ipp/print" % host, "ipp://%s/" % host]


def find_uri(uris):
    """the first address that answers and speaks AirPrint: (uri, probe) or raise SetupError"""
    last = None
    for uri in uris:
        try:
            p = probe(uri)
        except SetupError as e:
            last = e
            continue
        if p["airprint"]:
            return uri, p
        last = SetupError("no-airprint")
    raise last or SetupError("no answer")


# ---------------- changing the printer list ----------------
def _admin(cmds):
    """run lpadmin-style commands; when CUPS wants an administrator, ask once with the macOS
    password dialog for all of them"""
    for i, cmd in enumerate(cmds):
        code, out, err = _run(cmd, timeout=60)
        if code == 0:
            continue
        msg = (err or out).strip()
        if re.search(r"forbidden|not authori[sz]ed|unauthori[sz]ed|permission", msg, re.I):
            script = " && ".join(" ".join(shlex.quote(a) for a in c) for c in cmds[i:])
            code, out, err = _run(["osascript", "-e", "do shell script %s with administrator privileges"
                                   % _applescript_str(script)], timeout=300)
            if code != 0:
                raise SetupError("cancelled" if "-128" in err or "canceled" in err.lower() else err.strip()[:160])
            return
        raise SetupError(msg[:160] or "lpadmin failed")


def _applescript_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def queue_name(model, taken):
    base = re.sub(r"[^A-Za-z0-9]+", "_", model or "Printer").strip("_")[:96] or "Printer"
    name, n = base, 2
    low = {t.lower() for t in taken}
    while name.lower() in low:
        name, n = "%s_%d" % (base, n), n + 1
    return name


def setup(g, make_default=True, qs=None):
    """set the printer of group g up with AirPrint. Returns {"queue": name} or {"manual": True}
    (the macOS Add Printer window was opened); raises SetupError"""
    qs = queues() if qs is None else qs
    taken = [q["name"] for q in qs]
    cmds = []
    if g.get("best"):
        name = g["best"]
    elif g["via"] == "usb":
        if not g.get("connected") or not g.get("uri"):
            raise SetupError("not-connected")
        # macOS keeps the AirPrint description of a model it has set up once; reuse it
        model = _norm(g.get("model"))
        ppd = next((q["ppd"] for q in qs if q["airprint"] and q["ppd"] and model and _norm(q["model"]) == model), None)
        if not ppd:
            subprocess.Popen(["open", ADD_PRINTER])
            return {"manual": True}
        name = queue_name(g.get("model") or g["name"], taken)
        cmds.append(["lpadmin", "-p", name, "-D", g["name"], "-E", "-v", g["uri"], "-P", ppd,
                     "-o", "printer-is-shared=false"])
    else:
        cands = [g["uri"]] if g.get("uri") else []
        for q in g["queues"]:
            h = urllib.parse.urlsplit(q["uri"]).hostname
            if h:
                cands += [u for u in address_uris(h) if u not in cands]
        uri, info = find_uri(cands)
        name = queue_name(info["model"] or g["name"], taken)
        cmds.append(["lpadmin", "-p", name, "-D", info["info"] or info["model"] or g["name"], "-E", "-v", uri,
                     "-m", "everywhere", "-o", "printer-is-shared=false"])
    if make_default:
        cmds.append(["lpadmin", "-d", name])
    if cmds:
        _admin(cmds)      # one password prompt at most, for all of it
    return {"queue": name}


def add_address(text, make_default=False):
    """set up the AirPrint printer at an address the user typed"""
    uri, info = find_uri(address_uris(text))
    qs = queues()
    for q in qs:      # already there with AirPrint?
        if q["airprint"] and _host_key(q["uri"]) == _host_key(uri) and not q["offline"]:
            return {"queue": q["name"], "already": True}
    name = queue_name(info["model"] or "Printer", [q["name"] for q in qs])
    cmds = [["lpadmin", "-p", name, "-D", info["info"] or info["model"] or name, "-E", "-v", uri,
             "-m", "everywhere", "-o", "printer-is-shared=false"]]
    if make_default:
        cmds.append(["lpadmin", "-d", name])
    _admin(cmds)
    return {"queue": name}


def remove(names):
    """take entries out of the printer list"""
    names = [n for n in names if re.match(r"^[^\s/#]+$", n)]
    if names:
        _admin([["lpadmin", "-x", n] for n in names])


def make_default(name):
    _admin([["lpadmin", "-d", name]])


def test_page(name):
    """print the macOS test page"""
    for f in ("/System/Library/Frameworks/ApplicationServices.framework/Frameworks/PrintCore.framework/Resources/TestPage.pdf",
              "/usr/share/cups/data/testprint"):
        if os.path.exists(f):
            code, out, err = _run(["lp", "-d", name, "-t", "Test page", f])
            if code:
                raise SetupError((err or out).strip()[:160])
            return True
    raise SetupError("no test page")
