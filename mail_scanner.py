"""通过 IMAP 读取 Gmail，找出快递单号（只读，不会把邮件标记为已读）。"""
import email
import html as htmlmod
import imaplib
import re
from email.header import decode_header, make_header

from tracking_parser import find_tracking_numbers

GMAIL_HOST = "imap.gmail.com"
# Gmail 原生搜索语法（X-GM-RAW），只看最近的、可能含单号的邮件
DEFAULT_QUERY = (
    'newer_than:{days}d (tracking OR "tracking number" OR shipped OR shipment '
    'OR "out for delivery" OR delivered OR UPS OR FedEx OR USPS OR "on its way")'
)


def _decode(s):
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _html_to_text(h):
    # 保留 href 里的内容——很多单号只出现在 "Track package" 链接里
    hrefs = " ".join(re.findall(r'href=["\']([^"\']+)', h, re.I))
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return htmlmod.unescape(h) + " " + htmlmod.unescape(hrefs)


def _message_text(msg):
    parts = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition", "").lower().startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
        except Exception:
            continue
        if ctype == "text/plain":
            parts.append(text)
        elif ctype == "text/html":
            parts.append(_html_to_text(text))
    return "\n".join(parts)


def _all_mail_box(m):
    """找到“所有邮件”文件夹（中文界面下名字不是 All Mail，所以按 \\All 标记找）。"""
    typ, boxes = m.list()
    if typ == "OK":
        for b in boxes:
            line = b.decode("utf-8", errors="replace")
            if "\\All" in line:
                name = line.rsplit(' "/" ', 1)[-1].strip()
                return name if name.startswith('"') else '"%s"' % name
    return '"[Gmail]/All Mail"'


def scan_gmail(address, app_password, days=14, max_messages=200, log=print, progress=None):
    """返回 [{'number', 'carrier', 'title'}]

    progress(done, total, results) is called after each email (for the report in her balloon)."""
    results = []
    seen = set()
    m = imaplib.IMAP4_SSL(GMAIL_HOST)
    try:
        m.login(address, app_password)
        m.select(_all_mail_box(m), readonly=True)
        # 用 IMAP literal 传 Gmail 搜索语句，避免引号转义问题
        m.literal = DEFAULT_QUERY.format(days=days).encode("utf-8")
        typ, data = m.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")
        if typ != "OK":
            log("Gmail 搜索失败: %s" % typ)
            return results
        uids = data[0].split()[-max_messages:]
        log("Gmail: %d 封候选邮件" % len(uids))
        if progress:
            progress(0, len(uids), results)
        for k, uid in enumerate(reversed(uids)):  # 新邮件优先
            if progress and k:
                progress(k, len(uids), results)
            typ, msgdata = m.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not msgdata or not msgdata[0]:
                continue
            msg = email.message_from_bytes(msgdata[0][1])
            subject = _decode(msg.get("Subject"))
            sender = _decode(msg.get("From"))
            text = subject + "\n" + sender + "\n" + _message_text(msg)
            for number, carrier in find_tracking_numbers(text):
                if number in seen:
                    continue
                seen.add(number)
                results.append({"number": number, "carrier": carrier, "title": subject[:120]})
        if progress:
            progress(len(uids), len(uids), results)
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return results
