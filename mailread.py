"""Reading the inbox: Apple Mail (AppleScript) and Outlook (Microsoft Graph), plus a first sort.

Apple Mail
  The Mail app is asked through AppleScript (macOS asks once whether the widget may control
  Mail). Only messages newer than a cutoff are fetched: Mail answers that in a few seconds,
  where asking message by message takes minutes. If Mail isn't open, nothing is read (opening
  Mail behind your back would be rude); open_apple_mail() opens it when you ask.

Outlook (optional)
  The New Outlook for Mac doesn't let other apps read its mail, so the widget reads it from
  Microsoft directly: sign in once with a code (device code sign-in, no password is typed into
  the widget). That needs an "app ID" from Microsoft's app registration page (see the Mail
  settings tab). The sign-in is kept as a refresh token in the encrypted vault (vault.py).
  Only Mail.Read and User.Read are asked for: the widget can read mail, never send or delete.

The first sort (screen())
  Simple rules, no AI and nothing leaves the Mac: replies, real people, codes and "action
  needed" mail is important; job alerts, ads, newsletters and no-reply senders can be skipped;
  your own rules (always important / always skip) come first.
"""
import datetime
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

# ================= Apple Mail =================
# JavaScript for Automation: hands back clean JSON (AppleScript text mangles odd subjects)
_MAIL_JS = r'''
function run(argv){
  const hrs = +argv[0], maxn = +argv[1];
  const Mail = Application('Mail'), now = new Date(), cutoff = new Date(now - hrs * 3600e3), out = [];
  for (const a of Mail.accounts()){
    if (!a.enabled()) continue;
    const name = a.name();
    const box = a.mailboxes().find(b => ['INBOX', 'Inbox', '收件箱'].includes(b.name()));
    if (!box) continue;
    try {
      const ms = box.messages.whose({dateReceived: {'>': cutoff}});
      const s = ms.subject(), f = ms.sender(), d = ms.dateReceived(), r = ms.readStatus(), id = ms.messageId();
      for (let i = 0; i < Math.min(s.length, maxn); i++)
        out.push({account: name, mid: id[i], ts: d[i].getTime() / 1000, read: r[i], sender: f[i], subject: s[i]});
    } catch (e) { out.push({account: name, error: String(e)}); }
  }
  return JSON.stringify(out);
}
'''


class MailError(Exception):
    """kind: not_running | denied | error"""

    def __init__(self, kind, msg=""):
        super().__init__(msg or kind)
        self.kind = kind


def apple_running():
    try:
        r = subprocess.run(["osascript", "-e", 'application "Mail" is running'], capture_output=True, timeout=10)
        return r.stdout.decode().strip() == "true"
    except Exception:
        return False


def open_apple_mail():
    subprocess.Popen(["open", "-g", "-a", "Mail"])


def apple_recent(hours=24, limit=80):
    """newest inbox mail of the last `hours` from every Mail account (Mail must be open)"""
    if not apple_running():
        raise MailError("not_running")
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", "-", str(int(hours)), str(int(limit))],
                           input=_MAIL_JS.encode(), capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise MailError("error", "Mail took too long to answer")
    err = r.stderr.decode(errors="replace").strip()
    if r.returncode != 0:
        if "-1743" in err or "Not authorized" in err or "not allowed" in err.lower():
            raise MailError("denied", err)
        raise MailError("error", err.splitlines()[-1] if err else "osascript failed")
    try:
        rows = json.loads(r.stdout.decode(errors="replace") or "[]")
    except ValueError:
        raise MailError("error", "Mail's answer couldn't be read")
    out, errors = [], []
    for x in rows:
        if "error" in x:
            errors.append("%s: %s" % (x.get("account"), x["error"]))
            continue
        name, addr = split_sender(x.get("sender") or "")
        out.append({"id": "apple:" + str(x.get("mid")), "src": "apple", "account": x.get("account") or "",
                    "ts": round(x.get("ts") or time.time()), "read": bool(x.get("read")), "from": name,
                    "addr": addr, "subject": (x.get("subject") or "").strip(), "preview": "",
                    "mid": str(x.get("mid") or "")})
    if errors and not out:
        raise MailError("error", errors[0])
    return out


def apple_open(mid):
    """show one message in Mail"""
    subprocess.Popen(["open", "message://" + urllib.parse.quote("<%s>" % mid, safe="")])


def split_sender(s):
    """'Name <a@b.c>' -> ('Name', 'a@b.c')"""
    s = (s or "").strip()
    m = re.match(r'^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$', s)
    if m:
        return (m.group(1).strip() or m.group(2).strip()), m.group(2).strip().lower()
    return s, s.lower() if "@" in s else ""


# ================= Outlook / Microsoft Graph =================
AUTH = "https://login.microsoftonline.com/%s/oauth2/v2.0/"
GRAPH = "https://graph.microsoft.com/v1.0/"
SCOPES = "offline_access User.Read Mail.Read"
UA = "ParcelWidget"


class SignInNeeded(Exception):
    """the saved sign-in no longer works (expired, revoked, password changed): sign in again"""


class MSError(Exception):
    pass


def _post(url, form, timeout=30):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), method="POST",
                                 headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"error": "http_%d" % e.code}


def ms_device_start(client_id, tenant="common"):
    """start a sign-in: {user_code, verification_uri, device_code, interval, expires_at}"""
    d = _post(AUTH % tenant + "devicecode", {"client_id": client_id, "scope": SCOPES})
    if "device_code" not in d:
        raise MSError(_ms_err(d))
    d["expires_at"] = time.time() + int(d.get("expires_in", 900))
    d["interval"] = int(d.get("interval", 5))
    return d


def ms_device_poll(client_id, dev, tenant="common", stop=lambda: False):
    """wait for the sign-in to finish in the browser: the tokens, or None if stopped / expired"""
    interval = dev["interval"]
    while time.time() < dev["expires_at"]:
        for _ in range(interval * 4):
            if stop():
                return None
            time.sleep(0.25)
        d = _post(AUTH % tenant + "token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                             "client_id": client_id, "device_code": dev["device_code"]})
        e = d.get("error")
        if not e:
            d["expires_at"] = time.time() + int(d.get("expires_in", 3600)) - 60
            return d
        if e == "authorization_pending":
            continue
        if e == "slow_down":
            interval += 5
            continue
        if e == "expired_token":
            return None
        raise MSError(_ms_err(d))
    return None


def ms_refresh(client_id, refresh_token, tenant="common"):
    """new tokens from a refresh token (no window); SignInNeeded if Microsoft wants a new sign-in"""
    d = _post(AUTH % tenant + "token", {"grant_type": "refresh_token", "client_id": client_id,
                                         "refresh_token": refresh_token, "scope": SCOPES})
    e = d.get("error")
    if e in ("invalid_grant", "interaction_required", "consent_required", "login_required"):
        raise SignInNeeded(_ms_err(d))
    if e:
        raise MSError(_ms_err(d))
    d["expires_at"] = time.time() + int(d.get("expires_in", 3600)) - 60
    return d


# Microsoft's errors that need you to do something, in plain words on the page (ml.msE in i18n.js)
_AAD = {"700016": "app_unknown", "90002": "app_unknown", "50059": "single_tenant", "7000218": "public_off",
        "65001": "admin", "90094": "admin", "90095": "admin", "50105": "admin", "53003": "blocked",
        "50020": "tenant", "500200": "tenant", "50194": "tenant", "70000": "expired", "50076": "mfa"}


def _ms_err(d):
    """a short reason: one of _AAD's keys' values, or Microsoft's first sentence"""
    desc = (d.get("error_description") or "").split("\r\n")[0].split("\n")[0]
    m = re.match(r"AADSTS(\d+)", desc)
    if m and m.group(1) in _AAD:
        return _AAD[m.group(1)]
    desc = desc.split(" Trace ID")[0]
    return ("%s: %s" % (d.get("error"), desc[:160])) if desc else str(d.get("error") or "unknown error")


def _get(path, token, params=None):
    url = GRAPH + path + ("?" + urllib.parse.urlencode(params, safe="$,:' ") if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "User-Agent": UA,
                                               "Prefer": 'outlook.body-content-type="text"'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SignInNeeded("401")
        try:
            msg = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise MSError("HTTP %d %s" % (e.code, msg[:200]))


def ms_me(token):
    d = _get("me", token, {"$select": "userPrincipalName,mail,displayName"})
    return d.get("mail") or d.get("userPrincipalName") or "", d.get("displayName") or ""


def ms_recent(token, account, hours=24, limit=80):
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = _get("me/mailFolders/inbox/messages", token, {
        "$filter": "receivedDateTime ge %s" % since, "$orderby": "receivedDateTime desc", "$top": str(int(limit)),
        "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview,importance,inferenceClassification,webLink"})
    out = []
    for m in d.get("value", []):
        fr = (m.get("from") or {}).get("emailAddress") or {}
        try:
            ts = datetime.datetime.strptime(m["receivedDateTime"][:19], "%Y-%m-%dT%H:%M:%S") \
                .replace(tzinfo=datetime.timezone.utc).timestamp()
        except Exception:
            ts = time.time()
        out.append({"id": "ms:" + m["id"], "src": "outlook", "account": account, "ts": round(ts),
                    "read": bool(m.get("isRead")), "from": fr.get("name") or fr.get("address") or "",
                    "addr": (fr.get("address") or "").lower(), "subject": (m.get("subject") or "").strip(),
                    "preview": " ".join((m.get("bodyPreview") or "").split())[:160],
                    "url": m.get("webLink") or "", "high": m.get("importance") == "high",
                    "focused": m.get("inferenceClassification") == "focused"})
    return out


# ================= the first sort =================
PERSONAL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com",
            "mac.com", "yahoo.com", "qq.com", "163.com", "126.com", "foxmail.com", "proton.me", "protonmail.com"}
NOREPLY = re.compile(r"(^|[._-])(no-?reply|do-?not-?reply|donotreply|notifications?|notify|alerts?|newsletters?|"
                     r"news|marketing|promo(tions)?|mailer|digest|updates?|info|hello|team|support|jobs?|careers?|"
                     r"recruit(ing|ment)?|talent|bounce|automated|system)([._+-]|$)", re.I)
JOBS_DOMAINS = ("linkedin.com", "glassdoor.com", "indeed.com", "ziprecruiter.com", "monster.com", "dice.com",
                "handshake", "lever.co", "greenhouse.io", "workday", "smartrecruiters.com", "jobvite.com")
SOCIAL_DOMAINS = ("nextdoor.com", "facebookmail.com", "instagram.com", "twitter.com", "x.com", "pinterest.com",
                  "reddit", "quora.com", "medium.com", "tiktok.com", "youtube.com", "discord.com")
NEWS_DOMAINS = ("substack.com", "beehiiv.com", "mailchimp", "list-manage.com", "sendgrid", "mcsv.net",
                "convertkit", "ghost.io", "mailerlite", "klaviyo", "hubspot")
# mail sent from a marketing subdomain: e.example.com, email.example.com, e-offers.example.com, ...
R_BULK_HOST = re.compile(r"^(e|em|eml|email|emails|e-?mail|e-?offers?|offers?|enews|news|newsletters?|info|mail|mailer|"
                         r"mailing|marketing|promo|promos|member|members|go|connect|engage|reply|notice|notices|updates|"
                         r"comms|communications|campaign|crm|mkt|t|m|n|s|send|mg|ns|bounce)[0-9]*\.", re.I)
R_REPLY = re.compile(r"^\s*(re|aw|sv|antw|回复|答复)\s*[:：]", re.I)
R_CODE = re.compile(r"(verification|security|sign-?in|login|one-?time|confirm(ation)?)\s+code|\bOTP\b|\b2FA\b|"
                    r"验证码|校验码|动态码", re.I)
R_ACTION = re.compile(r"action (required|needed)|response (required|needed)|urgent|asap|deadline|due (today|tomorrow|soon)|"
                      r"overdue|expir(es|ing|ed)|final notice|past due|payment (failed|declined|due)|invoice|"
                      r"your (account|password)|password (reset|changed)|unusual (sign-?in|activity)|security alert|"
                      r"interview|offer letter|appointment|reminder:|meeting|invitation:|updated invitation|"
                      r"elect your|enroll(ment)?|sign (the|your)|signature (required|requested)|approv(e|al)|"
                      r"紧急|截止|到期|逾期|待办|请回复|面试|会议|账单|付款|安全提醒|密码", re.I)
R_JOBS = re.compile(r"jobs? (for you|alert|recommendation|matching)|now hiring|hiring|apply now|\band \d+ more jobs\b|"
                    r"job opportunit|positions? (open|available)|is hiring|招聘|职位推荐", re.I)
R_PROMO = re.compile(r"\d+\s*% off|\bsale\b|deal(s)?\b|discount|coupon|promo|free shipping|limited time|"
                     r"last chance|shop now|new arrivals|gear up|top picks|exclusive|save \$|black friday|"
                     r"cyber monday|webinar|newsletter|digest|unsubscribe|certif(ication|y) (course|path|training)|"
                     r"start your path|register now|join us|don't miss|new offers?|offers? (are )?inside|bonus miles|"
                     r"earn up to|rewards?|points|优惠|促销|折扣|限时|特价|订阅", re.I)
R_TXN = re.compile(r"\border\b|receipt|delivered|shipped|shipping|out for delivery|your package|confirmation|"
                   r"confirmed|booking|reservation|ticket|statement|订单|发货|已签收|收据|预订", re.I)


def _rules(text):
    """'a, b\\nc' -> ['a', 'b', 'c'] (lower case)"""
    return [x.strip().lower() for x in re.split(r"[,\n;，；]", text or "") if x.strip()]


def _hit(rules, m):
    hay = " ".join((m.get("addr", ""), m.get("from", ""), m.get("subject", ""))).lower()
    for r in rules:
        if r in hay:
            return r
    return None


def _base(dom):
    """mail.dept.example.co.uk -> example.co.uk; mail.uni.example.edu -> example.edu"""
    p = dom.split(".")
    n = 3 if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in ("co", "com", "ac", "edu", "org", "net", "gov") else 2
    return ".".join(p[-n:])


def screen(m, vip="", mute=""):
    """-> (level, reason): level 'important' | 'normal' | 'skip'"""
    acct = (m.get("account") or "").lower()
    subj = m.get("subject", "")
    addr = m.get("addr", "")
    local, _, dom = addr.partition("@")
    if _hit(_rules(vip), m):
        return "important", "vip"
    if _hit(_rules(mute), m):
        return "skip", "muted"
    if R_CODE.search(subj):
        return "important", "code"
    if m.get("high"):
        return "important", "high"
    bulk = bool(NOREPLY.search(local))
    if R_REPLY.search(subj) and not bulk:
        return "important", "reply"
    if any(d in dom for d in JOBS_DOMAINS) or R_JOBS.search(subj):
        return "skip", "jobs"
    if any(d in dom for d in SOCIAL_DOMAINS):
        return "skip", "social"
    if R_ACTION.search(subj):
        return "important", "action"
    if R_TXN.search(subj):
        return "normal", "txn"
    news = any(d in dom for d in NEWS_DOMAINS)
    if R_PROMO.search(subj) or R_BULK_HOST.match(dom) or news:
        return "skip", "news" if news else "promo"
    if bulk:
        return "skip", "noreply"
    if dom in PERSONAL:
        return "important", "person"
    own = acct.split("@")[1] if "@" in acct else ""
    if own and dom and own not in PERSONAL and _base(dom) == _base(own):
        return "important", "work"      # someone at your company / school (same domain as the account it came to)
    if m.get("focused"):
        return "normal", "focused"
    return "normal", ""


def sort_mail(items, vip="", mute=""):
    """screen every message; important first, then normal, then skip; newest first in each"""
    order = {"important": 0, "normal": 1, "skip": 2}
    for m in items:
        m["level"], m["why"] = screen(m, vip, mute)
    items.sort(key=lambda m: (order[m["level"]], -m["ts"]))
    return items
