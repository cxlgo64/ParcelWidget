"""Windows: the printers in Settings › Printers & scanners, grouped by the physical printer, and
one-click setup without a driver. The Windows side of airprint.py (same functions, same shapes).

What macOS calls AirPrint, Windows does with its "Microsoft IPP Class Driver": Windows asks
the printer what it can do (IPP Everywhere / Mopria / AirPrint printers all answer) and needs
no driver from the maker. This module
  - groups the printer list by physical printer (the same printer is often there twice: once
    found over the network, once added by hand; or an old entry that no longer answers);
  - sets a network printer up without a driver in one go (Add-Printer -IppURL, after asking
    the printer whether it speaks IPP); USB printers are set up by Windows itself when they're
    plugged in - if one isn't in the list, Settings › Printers & scanners opens;
  - removes the duplicates of a printer, makes an entry the default, prints a test page.
Entries that aren't printers (Print to PDF, XPS, OneNote, Fax) are left out.

groups(usb_devices) -> [group], each:
    key, name, via: usb|network|bonjour|other, connected (USB: plugged in), uri,
    queues [{name, uri, desc, model (the driver's name), airprint (no maker's driver), offline, default}],
    best (queue name or None), extra (the other entries), default, can_setup,
    status: ready (an entry works) | offline (only entries that don't answer) | none (not in the list)
On Windows the maker's own driver is as good as none at all, so there is no "other" status.
"""
import json
import re
import socket
import ssl
import struct
import time
import urllib.parse
import urllib.request

from plat import open_path, powershell

ADD_PRINTER = "ms-settings:printers"
DRIVERLESS = ("microsoft ipp class driver", "universal print class driver")
NOT_PRINTERS = re.compile(r"print to pdf|xps document writer|onenote|\bfax\b|send to |remote desktop easy print|"
                          r"pdf(creator| writer|24)?$|snagit|cutepdf|foxit|adobe pdf", re.I)
NOT_PORTS = ("portprompt:", "nul:", "shrfax:", "file:", "xpsport:")
AIRPRINT_FORMATS = ("image/urf", "image/pwg-raster", "application/pdf")


class SetupError(Exception):
    """a step failed; str() is short enough to show"""


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", urllib.parse.unquote(str(s or "")).lower())


# ---------------- the printer list ----------------
_LIST_PS = r'''
$p = @(Get-CimInstance Win32_Printer | Select-Object Name,DriverName,PortName,Default,WorkOffline,PrinterStatus,Location)
$t = @(Get-CimInstance Win32_TCPIPPrinterPort | Select-Object Name,HostAddress)
ConvertTo-Json -InputObject @{ printers = $p; ports = $t } -Compress -Depth 3
'''


def _host_in(text):
    """an address or host name inside a port name or a location ("http://10.0.0.5:80/WebServices/Device")"""
    text = str(text or "")
    m = re.search(r"\w+://\[?([A-Za-z0-9.\-:]+?)\]?(?::\d+)?(?:/|$)", text)
    if m:
        return m.group(1).lower()
    m = re.search(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])", text)
    return m.group(1) if m else ""


def queues():
    """[{name, uri, desc, model, airprint, offline, default, port, host}] of the printer list"""
    code, out, err = powershell(_LIST_PS, timeout=60)
    if code != 0:
        raise SetupError(err.splitlines()[0][:160] if err else "couldn't read the printer list")
    try:
        d = json.loads(out.strip() or "{}")
    except ValueError:
        raise SetupError("couldn't read the printer list")
    hosts = {str(t.get("Name") or "").lower(): str(t.get("HostAddress") or "") for t in d.get("ports") or [] if t}
    qs = []
    for p in d.get("printers") or []:
        if not p or not p.get("Name"):
            continue
        name, driver, port = str(p["Name"]), str(p.get("DriverName") or ""), str(p.get("PortName") or "")
        if NOT_PRINTERS.search(name) or NOT_PRINTERS.search(driver) or port.lower() in NOT_PORTS:
            continue
        usb = bool(re.match(r"^(USB|DOT4)", port, re.I))
        host = "" if usb else (hosts.get(port.lower()) or _host_in(port) or _host_in(p.get("Location"))).lower()
        qs.append({"name": name, "desc": name, "model": driver, "port": port, "host": host,
                   "uri": ("usb://" + port) if usb else ("ipp://" + host) if host else port,
                   "airprint": driver.lower() in DRIVERLESS, "default": bool(p.get("Default")),
                   "offline": bool(p.get("WorkOffline")) or p.get("PrinterStatus") == 7, "ppd": None})
    return qs


def _host_key(uri):
    u = urllib.parse.urlsplit(uri if "://" in uri else "ipp://" + uri)
    return "net:" + (u.hostname or "").lower().rstrip(".")


def _same(a, b):
    """do two names mean the same printer model? ("HP LaserJet P1005" / "LaserJet P1005 (Copy 1)")"""
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a)


def queue_for(dev, qs=None):
    """the printer list entry of a plugged-in USB printer, or None"""
    qs = queues() if qs is None else qs
    usb = [q for q in qs if q["uri"].startswith("usb://")]
    for q in usb:
        if _same(dev.get("name"), q["name"]) or _same(dev.get("name"), q["model"]) or \
                (dev.get("product_db") and (_same(dev["product_db"], q["name"]) or _same(dev["product_db"], q["model"]))):
            return q["name"]
    return None


def groups(usb_devices=(), qs=None, found=()):
    """the printer list grouped by physical printer (see the module doc). usb_devices: printers from
    usbscan_win.scan(); found: printers found nearby (discover())"""
    qs = queues() if qs is None else qs
    out, by_key = [], {}

    def group(key, **kw):
        g = by_key.get(key)
        if not g:
            g = by_key[key] = dict({"key": key, "queues": [], "connected": False, "uri": None}, **kw)
            out.append(g)
        return g

    left = list(qs)
    usb = [d for d in usb_devices if d.get("kind") == "printer"]
    for d in usb:       # plugged-in USB printers first
        g = group("usb:" + (_norm(d.get("serial")) or _norm(d["name"])), name=d["name"], via="usb", connected=True,
                  model=d["name"])
        mine = [q for q in left if q["uri"].startswith("usb://") and
                (_same(d["name"], q["name"]) or _same(d["name"], q["model"]) or _same(d.get("product_db"), q["name"]))]
        if not mine and len(usb) == 1:      # the only USB printer and the only USB entries: it's them
            mine = [q for q in left if q["uri"].startswith("usb://")]
        for q in mine:
            g["queues"].append(q)
            left.remove(q)
    for q in left:
        if q["uri"].startswith("usb://"):
            g = group("usb:" + _norm(q["model"] or q["name"]), name=q["name"], via="usb", model=q["model"])
        elif q["host"]:
            g = group("net:" + q["host"], name=q["name"], via="network", model=q["model"])
        else:
            g = group("other:" + _norm(q["name"]), name=q["name"], via="other", model=q["model"])
        g["queues"].append(q)
    for f in found:
        key = _host_key(f["uri"])
        g = by_key.get(key) or next((x for x in out if x["via"] == "network" and f.get("host") and
                                     x["key"] == "net:" + f["host"].lower().rstrip(".")), None)
        if not g:
            g = group(key, name=f["name"], via="bonjour", model=f.get("model", ""))
        g["uri"] = g.get("uri") or f["uri"]
        g["found"] = True
    for g in out:
        _rate(g)
    return out


def _rate(g):
    qs = g["queues"]
    if g["via"] == "network" and not g.get("uri") and qs:
        g["uri"] = "ipp://%s/ipp/print" % qs[0]["host"]
    working = [q for q in qs if not q["offline"]]
    best = max(working, key=lambda q: (q["default"], q["airprint"])) if working else None
    g["best"] = best["name"] if best else None
    g["status"] = "ready" if best else "offline" if qs else "none"
    g["extra"] = [q["name"] for q in qs if q["name"] != g["best"]] if best else []
    g["default"] = bool(best and best["default"])
    g["server"] = False
    # USB printers are Windows' own business (plug and play); the button opens Settings for those not in the list
    g["can_setup"] = g["via"] in ("network", "bonjour") or (g["via"] == "usb" and g["connected"])
    g["name"] = g.get("name") or g.get("model") or "Printer"


# ---------------- finding printers nearby (mDNS / Bonjour, spoken here directly) ----------------
MDNS = ("224.0.0.251", 5353)


def _dns_name(data, pos, depth=0):
    """a (possibly compressed) DNS name at pos: (labels, position after it)"""
    labels, end = [], None
    while pos < len(data) and depth < 20:
        n = data[pos]
        if n == 0:
            pos += 1
            break
        if n & 0xC0 == 0xC0:
            if pos + 1 >= len(data):
                break
            if end is None:
                end = pos + 2
            pos = ((n & 0x3F) << 8) | data[pos + 1]
            depth += 1
            continue
        labels.append(data[pos + 1:pos + 1 + n].decode("utf-8", "replace"))
        pos += 1 + n
    return labels, (end if end is not None else pos)


def _dns_records(data):
    """the answers in a DNS message: [(name labels, type, rdata start, rdata length)]"""
    if len(data) < 12:
        return []
    qd, an, ns, ar = struct.unpack(">4H", data[4:12])
    pos = 12
    for _ in range(qd):
        _, pos = _dns_name(data, pos)
        pos += 4
    out = []
    for _ in range(an + ns + ar):
        if pos >= len(data):
            break
        name, pos = _dns_name(data, pos)
        if pos + 10 > len(data):
            break
        typ, _cls, _ttl, n = struct.unpack(">HHIH", data[pos:pos + 10])
        pos += 10
        out.append((name, typ, pos, n))
        pos += n
    return out


def _dns_query(names):
    msg = struct.pack(">6H", 0, 0, len(names), 0, 0, 0)
    for n in names:
        for label in n.strip(".").split("."):
            msg += bytes([len(label)]) + label.encode()
        msg += b"\x00" + struct.pack(">HH", 12, 0x8001)       # PTR, class IN, "answer me directly"
    return msg


def _parse_mdns(packets):
    """[{name, uri, model, uuid, host}] from mDNS answers: the printers that need no driver"""
    ptr, srv, txt, addr = {}, {}, {}, {}
    for data in packets:
        for name, typ, pos, n in _dns_records(data):
            key = ".".join(name).lower()
            if typ == 12:                                       # PTR: service type -> instance
                target, _ = _dns_name(data, pos)
                if len(name) >= 2 and name[0].lower() in ("_ipp", "_ipps") and target:
                    ptr[".".join(target).lower()] = (target[0], name[0].lower() == "_ipps")
            elif typ == 33 and n >= 6:                          # SRV: instance -> host and port
                port = struct.unpack(">H", data[pos + 4:pos + 6])[0]
                host, _ = _dns_name(data, pos + 6)
                srv[key] = (".".join(host), port)
            elif typ == 16:                                     # TXT: instance -> what it can do
                kv, p = {}, pos
                while p < pos + n:
                    ln = data[p]
                    item = data[p + 1:p + 1 + ln].decode("utf-8", "replace")
                    p += 1 + ln
                    if "=" in item:
                        k, v = item.split("=", 1)
                        kv[k.lower()] = v
                txt[key] = kv
            elif typ == 1 and n == 4:                           # A: host -> address
                addr[key] = socket.inet_ntoa(data[pos:pos + 4])
    res = {}
    for inst, (label, secure) in ptr.items():
        if inst not in srv:
            continue
        host, port = srv[inst]
        t = txt.get(inst, {})
        pdl = t.get("pdl", "").lower()
        if not (t.get("urf") or any(f in pdl for f in AIRPRINT_FORMATS)):
            continue                                            # needs its maker's driver
        ip = addr.get(host.lower())
        uri = "%s://%s:%d/%s" % ("ipps" if secure else "ipp", ip or host.rstrip("."), port, t.get("rp", "ipp/print").lstrip("/"))
        key = t.get("uuid") or label
        if key not in res or secure:
            res[key] = {"name": label, "uri": uri, "model": t.get("ty") or label, "uuid": t.get("uuid", ""),
                        "host": ip or host.rstrip(".")}
    return list(res.values())


def discover(timeout=4):
    """printers announced nearby that need no driver: [{name, uri, model, uuid, host}]"""
    packets = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.bind(("", 0))
        q = _dns_query(["_ipp._tcp.local", "_ipps._tcp.local"])
        try:        # every network this PC is on (Wi-Fi, cable, a VPN...), not just the main one
            nets = [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")]
        except OSError:
            nets = []
        end = time.time() + timeout
        sent = 0
        while time.time() < end:
            if time.time() >= sent + 1.5:       # ask again now and then: answers get lost
                for ip in nets or [None]:
                    try:
                        if ip:
                            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
                        s.sendto(q, MDNS)
                    except OSError:
                        pass
                sent = time.time()
            s.settimeout(0.3)
            try:
                data, _ = s.recvfrom(9000)
                packets.append(data)
            except socket.timeout:
                pass
            except OSError:
                break
        s.close()
    except OSError:
        pass
    return _parse_mdns(packets)


# ---------------- asking a printer what it is (IPP, spoken here directly) ----------------
def _ipp_request(uri, wanted):
    def attr(tag, name, value):
        n, v = name.encode(), value.encode()
        return bytes([tag]) + struct.pack(">H", len(n)) + n + struct.pack(">H", len(v)) + v
    body = struct.pack(">HHI", 0x0200, 0x000B, 1) + b"\x01"            # IPP 2.0, Get-Printer-Attributes
    body += attr(0x47, "attributes-charset", "utf-8") + attr(0x48, "attributes-natural-language", "en")
    body += attr(0x45, "printer-uri", uri)
    for i, w in enumerate(wanted):
        body += attr(0x44, "requested-attributes" if i == 0 else "", w)
    return body + b"\x03"


def _ipp_parse(data):
    """(status, {attribute: [values]}) of an IPP answer; text values only"""
    if len(data) < 8:
        raise ValueError("short answer")
    status = struct.unpack(">H", data[2:4])[0]
    pos, attrs, last = 8, {}, None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == 0x03:
            break
        if tag < 0x10:          # the start of a group of attributes
            continue
        if pos + 2 > len(data):
            break
        n = struct.unpack(">H", data[pos:pos + 2])[0]
        name = data[pos + 2:pos + 2 + n].decode("utf-8", "replace")
        pos += 2 + n
        if pos + 2 > len(data):
            break
        m = struct.unpack(">H", data[pos:pos + 2])[0]
        value = data[pos + 2:pos + 2 + m]
        pos += 2 + m
        last = name or last     # no name: one more value of the attribute before
        if last:
            attrs.setdefault(last, []).append(value.decode("utf-8", "replace"))
    return status, attrs


def http_url(uri):
    """ipp://host/path -> http://host:631/path (IPP travels over HTTP)"""
    u = urllib.parse.urlsplit(uri)
    scheme = "https" if u.scheme in ("ipps", "https") else "http"
    host = u.hostname or ""
    if ":" in host:
        host = "[%s]" % host
    return "%s://%s:%d%s" % (scheme, host, u.port or 631, u.path or "/")


def probe(uri):
    """ask a network printer what it is: {model, info, uuid, airprint} or raise SetupError"""
    url = http_url(uri)
    req = urllib.request.Request(url, data=_ipp_request(uri, ["printer-make-and-model", "printer-info", "printer-uuid",
                                                              "document-format-supported", "urf-supported"]),
                                 headers={"Content-Type": "application/ipp"}, method="POST")
    ctx = None
    if url.startswith("https:"):        # printers sign their own certificates
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            status, attrs = _ipp_parse(r.read(200000))
    except Exception as e:
        raise SetupError("no answer" if isinstance(e, (OSError, socket.timeout)) else str(e)[:160])
    if status >= 0x0100:
        raise SetupError("no answer")
    fmts = [f.lower() for f in attrs.get("document-format-supported", [])]
    one = lambda k: (attrs.get(k) or [""])[0]     # noqa: E731
    return {"model": one("printer-make-and-model"), "info": one("printer-info"), "uuid": one("printer-uuid"),
            "airprint": any(f in fmts for f in AIRPRINT_FORMATS) or bool(attrs.get("urf-supported"))}


def address_uris(text):
    """what to try for an address the user typed: an ipp(s):// URL as is, else host -> the usual paths"""
    text = text.strip()
    if re.match(r"^ipps?://", text):
        return [text]
    host = re.sub(r"^\w+://", "", text).split("/")[0]
    if not re.match(r"^[A-Za-z0-9.\-:\[\]]+$", host or ""):
        raise SetupError("bad address")
    return ["ipp://%s/ipp/print" % host, "ipps://%s/ipp/print" % host, "ipp://%s/" % host]


def find_uri(uris):
    """the first address that answers and needs no driver: (uri, probe) or raise SetupError"""
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
_ADD_PS = r'''
$before = @(Get-Printer | ForEach-Object { $_.Name })
Add-Printer -IppURL $env:PW_ARG0
$new = @(Get-Printer | Where-Object { $before -notcontains $_.Name } | ForEach-Object { $_.Name })
if ($new.Count) { Write-Output ("added:" + $new[0]) } else { Write-Output "added:" }
'''
_DEFAULT_PS = "(New-Object -ComObject WScript.Network).SetDefaultPrinter($env:PW_ARG0)"
_REMOVE_PS = "Remove-Printer -Name $env:PW_ARG0"
_TEST_PS = ("$p = Get-CimInstance Win32_Printer | Where-Object { $_.Name -eq $env:PW_ARG0 }; "
            "if (-not $p) { throw 'no such printer' }; "
            "$r = Invoke-CimMethod -InputObject $p -MethodName PrintTestPage; if ($r.ReturnValue -ne 0) { throw 'failed' }")


def _ps(script, args, timeout=120):
    """run a change to the printer list; when Windows wants an administrator, ask (once) and run it again"""
    code, out, err = powershell(script, args, timeout=timeout)
    if code != 0 and re.search(r"access is denied|0x80070005|拒绝访问|administrator|elevat", err, re.I):
        code, out, err = powershell(script, args, timeout=300, elevate=True)
        if code != 0:
            raise SetupError("cancelled")
    if code != 0:
        raise SetupError((err.splitlines()[0] if err else "failed")[:160])
    return out


def _add(uri):
    """add the printer at an IPP address without a driver. The new entry's name, or None when this
    Windows can't (before Windows 10 version 2004): then Settings opens."""
    last = None
    for u in (uri, http_url(uri)):        # newer Windows takes ipp://, some builds only http://
        code, out, err = powershell(_ADD_PS, [u], timeout=180)
        if code == 0:
            m = re.search(r"^added:(.*)$", out, re.M)
            return (m.group(1).strip() if m else "") or True
        if re.search(r"parameter.*IppURL|IppURL.*parameter", err, re.I | re.S):
            open_path(ADD_PRINTER)
            return None
        if re.search(r"access is denied|0x80070005|拒绝访问", err, re.I):
            code, out, err = powershell(_ADD_PS, [u], timeout=300, elevate=True)
            if code == 0:
                return True
            raise SetupError("cancelled")
        last = err
    raise SetupError((last.splitlines()[0] if last else "failed")[:160])


def setup(g, make_default=True, qs=None):
    """set the printer of group g up without a driver. Returns {"queue": name} or {"manual": True}
    (Settings › Printers & scanners was opened); raises SetupError"""
    if g.get("best"):
        name = g["best"]
    elif g["via"] == "usb":
        if not g.get("connected"):
            raise SetupError("not-connected")
        open_path(ADD_PRINTER)        # Windows sets USB printers up itself; "Add device" there nudges it
        return {"manual": True}
    else:
        cands = [g["uri"]] if g.get("uri") else []
        for q in g["queues"]:
            if q.get("host"):
                cands += [u for u in address_uris(q["host"]) if u not in cands]
        uri, info = find_uri(cands)
        name = _add(uri)
        if name is None:
            return {"manual": True}
        if name is True:              # added, but under which name? look for it
            name = next((q["name"] for q in queues() if q["host"] and q["host"] == (urllib.parse.urlsplit(uri).hostname or "")),
                        info["model"] or g["name"])
    if make_default and name:
        _ps(_DEFAULT_PS, [name])
    return {"queue": name}


def add_address(text, make_default=False):
    """set up the printer at an address the user typed"""
    uri, info = find_uri(address_uris(text))
    host = (urllib.parse.urlsplit(uri).hostname or "").lower()
    for q in queues():      # already there?
        if q["host"] == host and not q["offline"]:
            return {"queue": q["name"], "already": True}
    name = _add(uri)
    if name is None:
        return {"manual": True}
    if name is True:
        name = next((q["name"] for q in queues() if q["host"] == host), info["model"] or host)
    if make_default:
        _ps(_DEFAULT_PS, [name])
    return {"queue": name}


def remove(names):
    """take entries out of the printer list"""
    for n in names:
        _ps(_REMOVE_PS, [n])


def make_default(name):
    _ps(_DEFAULT_PS, [name])


def test_page(name):
    """print Windows' test page"""
    _ps(_TEST_PS, [name])
    return True
