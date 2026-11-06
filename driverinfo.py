"""Online lookups for the USB check (features/usb.py). All slow, all cached in APP_DIR/cache.

vendor_names(vid, pid)        names from the public USB ID database (linux-usb.org/usb.ids)
macos_updates()               pending macOS updates (softwareupdate --list): Apple's own drivers
                              are part of macOS and only get newer with it
search(query)                 top web results (DuckDuckGo), for drivers that aren't Apple's
find_printer_driver(mfg, mdl) Apple's printer driver package that supports this model
download_printer_driver(...)  download it into ~/Downloads/Printer Drivers
"""
import html
import json
import os
import plistlib
import re
import subprocess
import time
import urllib.parse
import urllib.request

from core import APP_DIR, log

CACHE = os.path.join(APP_DIR, "cache")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
USB_IDS = "http://www.linux-usb.org/usb.ids"
# Apple's software update catalog: its printer driver packages say which models they support
CATALOG = ("https://swscan.apple.com/content/catalogs/others/index-26-15-14-13-12-10.16-10.15-10.14-10.13-10.12-"
           "10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog")
# Apple's single installer for HP printers (support.apple.com/kb/DL1888); the catalog's HP
# product is the same drivers split into 47 pieces
HP_DMG_PAGE = "https://support.apple.com/kb/DL1888?locale=en_US"
DOWNLOADS = os.path.expanduser("~/Downloads/Printer Drivers")
APPLE_HOSTS = (".apple.com", ".cdn-apple.com")   # Apple's servers only


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cached(name, max_age, fetch):
    """bytes of cache/<name>, fetched again when older than max_age seconds (or on error, the old copy)"""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        with open(path, "rb") as f:
            return f.read()
    try:
        data = fetch()
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
        return data
    except Exception as e:
        log("usb: couldn't fetch %s: %r" % (name, e))
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        raise


# ---------------- vendor names ----------------
_ids = None


def vendor_names(vid, pid):
    """(vendor, product) from the USB ID database, or ("", "")"""
    global _ids
    if _ids is None:
        _ids = {}
        raw = _cached("usb.ids", 30 * 86400, lambda: _get(USB_IDS, 60)).decode("latin-1")
        cur = None
        for line in raw.splitlines():
            if not line or line.startswith("#"):
                continue
            if line.startswith("C "):           # device classes follow: done with vendors
                break
            if not line.startswith("\t"):
                v, _, name = line.partition("  ")
                cur = v.strip().lower()
                _ids[cur] = (name.strip(), {})
            elif cur and not line.startswith("\t\t"):
                p, _, name = line.strip().partition("  ")
                _ids[cur][1][p.lower()] = name.strip()
    v = _ids.get(vid.lower())
    if not v:
        return "", ""
    return v[0], v[1].get(pid.lower(), "")


# ---------------- macOS updates (Apple's drivers) ----------------
def macos_version():
    return subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip()


def macos_updates(max_age=12 * 3600):
    """{"checked": ts, "updates": [{"title", "version"}]} - softwareupdate asks Apple's servers"""
    path = os.path.join(CACHE, "softwareupdate.json")
    try:
        with open(path) as f:
            c = json.load(f)
        if time.time() - c["checked"] < max_age and c.get("os") == macos_version():
            return c
    except Exception:
        pass
    out = subprocess.run(["softwareupdate", "--list"], capture_output=True, text=True, timeout=300)
    text = out.stdout + out.stderr
    ups = []
    for m in re.finditer(r"Title: ([^,\n]+), Version: ([^,\n]+)", text):
        ups.append({"title": m.group(1).strip(), "version": m.group(2).strip()})
    if not ups and "No new software available" not in text and out.returncode != 0:
        raise RuntimeError(text.strip().splitlines()[-1] if text.strip() else "softwareupdate failed")
    c = {"checked": time.time(), "os": macos_version(), "updates": ups}
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(c, f)
    return c


# ---------------- web search (third-party drivers) ----------------
def search(query, n=3):
    """[{title, url}] - the top web results"""
    raw = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query), 20).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S):
        href = html.unescape(m.group(1))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = q.get("uddg", [href])[0]
        if url.startswith("//"):
            url = "https:" + url
        if "duckduckgo.com/y.js" in url:      # ads
            continue
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        out.append({"title": title, "url": url})
        if len(out) >= n:
            break
    return out


def newest_version_in(texts):
    """the highest version number mentioned, e.g. "v2.10.3" -> "2.10.3" (a hint, not a fact)"""
    best = None
    for t in texts:
        for m in re.finditer(r"(?:version|ver\.?|v)\s?(\d+(?:\.\d+){1,3})", t, re.I):
            v = m.group(1)
            if best is None or vkey(v) > vkey(best):
                best = v
    return best


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4])


# ---------------- printer drivers ----------------
def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _vendor_key(mfg):
    m = _norm(mfg)
    for k, names in {"HP": ("hp", "hewlettpackard"), "Canon": ("canon",), "EPSON": ("epson", "seiko"),
                     "Brother": ("brother",), "Lexmark": ("lexmark",), "Samsung": ("samsung",),
                     "Xerox": ("xerox",), "FujiXerox": ("fujixerox", "fujifilm"), "Ricoh": ("ricoh",),
                     "Gestetner": ("gestetner",), "Lanier": ("lanier",), "Savin": ("savin",),
                     "Infotec": ("infotec",), "NRG": ("nrg",), "InfoPrint": ("infoprint",)}.items():
        if any(m.startswith(n) for n in names):
            return k
    return None


def find_printer_driver(mfg, mdl):
    """Apple's driver package for this printer model: {"vendor", "product", "title", "date", "size",
    "packages": [{url, size}], "dist"} or None"""
    vendor = _vendor_key(mfg) or _vendor_key(mdl)
    if not vendor:
        return None
    cat = plistlib.loads(_cached("printers.sucatalog", 7 * 86400, lambda: _get(CATALOG, 120)))
    best = None
    for pid, p in cat.get("Products", {}).items():
        smd = p.get("ServerMetadataURL", "")
        if not smd.endswith("/%s_PrinterSupport.smd" % vendor):
            continue
        if best is None or p.get("PostDate") > best[1].get("PostDate"):
            best = (pid, p)
    if not best:
        return None
    pid, p = best
    d = p.get("Distributions", {})
    durl = d.get("English") or d.get("en") or next(iter(d.values()), None)
    if not durl:
        return None
    dist = _cached("%s.dist" % pid, 30 * 86400, lambda: _get(durl, 120)).decode("utf-8", "replace")
    want = _norm(mdl)
    vend = _norm(vendor)
    models = set()
    for m in re.finditer(r"<tag>MANUFACTURER:[^;<]*;MODEL:([^<]+)</tag>", dist):
        models.add(_norm(m.group(1)))
    # "HP LaserJet P1005" vs "LaserJet P1005": compare with and without the maker's name
    if not any(x in (want, vend + want) or (x.startswith(vend) and x[len(vend):] == want) for x in models):
        return None
    pk = p.get("Packages", [])
    if vendor == "HP":
        # what gets downloaded for HP is Apple's newer one-file installer: show its date and size
        try:
            dmg = _hp_dmg()
            m = re.search(r"-(20\d\d)(\d\d)(\d\d)-", dmg["url"]) if dmg else None
            if m:
                return {"vendor": vendor, "product": pid, "date": "-".join(m.groups()), "size": dmg["size"],
                        "packages": [], "dist": durl, "title": "HP Printer Drivers"}
        except Exception:
            pass
    return {"vendor": vendor, "product": pid, "date": str(p.get("PostDate", ""))[:10],
            "size": sum(x.get("Size", 0) for x in pk), "packages": [{"url": x["URL"], "size": x.get("Size", 0)} for x in pk],
            "dist": durl, "title": "%s Printer Drivers" % vendor}


def _hp_dmg():
    """{"url", "size"} of Apple's single HP printer driver installer"""
    page = _get(HP_DMG_PAGE, 30).decode("utf-8", "replace")
    m = re.search(r'https://updates\.cdn-apple\.com/[^"\']+HewlettPackardPrinterDrivers\.dmg', page)
    if not m:
        return None
    req = urllib.request.Request(m.group(0), method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return {"url": m.group(0), "size": int(r.headers.get("Content-Length") or 0)}


def _download(url, dest, progress, should_stop, done_before=0, total=0):
    host = urllib.parse.urlparse(url).hostname or ""
    if not url.startswith("https://") or not host.endswith(APPLE_HOSTS):
        raise RuntimeError("refusing to download from %s" % host)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    got = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
        while True:
            if should_stop():
                raise InterruptedError("cancelled")
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            progress(done_before + got, total)
    os.replace(dest + ".part", dest)
    return got


def download_printer_driver(drv, progress=lambda done, total: None, should_stop=lambda: False):
    """Download the driver into ~/Downloads/Printer Drivers. Returns the file to open to install it.
    HP: Apple's one-file installer (.dmg). Others: the catalog's packages, put together into one
    installer with productbuild. Everything comes from Apple's servers over https, and
    the packages must carry Apple's signature."""
    os.makedirs(DOWNLOADS, exist_ok=True)
    if drv["vendor"] == "HP":
        dmg = _hp_dmg()
        if dmg:
            dest = os.path.join(DOWNLOADS, "HewlettPackardPrinterDrivers.dmg")
            if not (os.path.exists(dest) and os.path.getsize(dest) == dmg["size"]):
                _download(dmg["url"], dest, progress, should_stop, 0, dmg["size"])
            return dest
    work = os.path.join(DOWNLOADS, ".%s-%s" % (drv["vendor"], drv["product"]))
    os.makedirs(work, exist_ok=True)
    total, done = drv["size"], 0
    for p in drv["packages"]:
        dest = os.path.join(work, p["url"].rsplit("/", 1)[-1])
        if not (os.path.exists(dest) and os.path.getsize(dest) == p["size"]):
            _download(p["url"], dest, progress, should_stop, done, total)
        done += p["size"]
        progress(done, total)
        sig = subprocess.run(["pkgutil", "--check-signature", dest], capture_output=True, text=True).stdout
        if "Apple" not in sig or "signed" not in sig.lower():
            raise RuntimeError("%s isn't signed by Apple" % os.path.basename(dest))
    dist = os.path.join(work, "%s.dist" % drv["product"])
    text = _get(drv["dist"], 120).decode("utf-8", "replace")
    # these packages predate Apple silicon: let Installer run them there too (with Rosetta)
    text = re.sub(r"hostArchitectures=(['\"])[^'\"]*\1", "hostArchitectures='x86_64,arm64'", text)
    with open(dist, "w", encoding="utf-8") as f:
        f.write(text)
    out = os.path.join(DOWNLOADS, "%s.pkg" % drv["title"])
    r = subprocess.run(["productbuild", "--distribution", dist, "--package-path", work, out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("productbuild: " + (r.stderr or r.stdout).strip()[-200:])
    return out
