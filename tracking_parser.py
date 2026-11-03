"""从邮件文本中识别快递单号，并判断承运商。"""
import re

# 有明显特征的单号：直接认
UPS_RE = re.compile(r"\b1Z[0-9A-Z]{16}\b")
AMAZON_RE = re.compile(r"\bTBA\d{12}\b")
USPS_INTL_RE = re.compile(r"\b[A-Z]{2}\d{9}US\b")
# 纯数字单号：需要邮件里出现承运商关键词才认，避免把订单号/电话当单号
USPS_NUM_RE = re.compile(r"(?<!\d)(9[1-5]\d{20}|9[1-5]\d{24})(?!\d)")
FEDEX_NUM_RE = re.compile(r"(?<!\d)(\d{12}|\d{15}|\d{20}|\d{22})(?!\d)")


def _has(text, *words):
    t = text.lower()
    return any(w in t for w in words)


def _plausible(num):
    # 排除 000000000000 / 111111111111 这类
    return len(set(num)) > 2


def find_tracking_numbers(text):
    """返回 [(tracking_number, carrier), ...]，已去重、保持出现顺序。"""
    if not text:
        return []
    # 把 URL 里的 %20 等去掉，单号经常藏在链接里
    text = text.replace("%20", " ")
    found = {}

    def add(num, carrier):
        num = num.upper()
        if num not in found:
            found[num] = carrier

    for m in UPS_RE.finditer(text.upper()):
        add(m.group(0), "UPS")
    for m in AMAZON_RE.finditer(text.upper()):
        add(m.group(0), "Amazon")
    for m in USPS_INTL_RE.finditer(text.upper()):
        add(m.group(0), "USPS")

    mentions_usps = _has(text, "usps", "postal service")
    mentions_fedex = _has(text, "fedex", "fed ex")
    mentions_track = _has(text, "track", "shipment", "shipped", "delivery", "package")

    if mentions_track:
        for m in USPS_NUM_RE.finditer(text):
            n = m.group(1)
            if not _plausible(n):
                continue
            if mentions_usps or not mentions_fedex:
                add(n, "USPS")
            else:
                add(n, "FedEx")  # FedEx Ground Economy 也会用 92 开头的 22 位单号
        if mentions_fedex:
            for m in FEDEX_NUM_RE.finditer(text):
                n = m.group(1)
                if n in found or not _plausible(n):
                    continue
                add(n, "FedEx")
    return list(found.items())


def guess_carrier(num):
    """手动添加单号时猜承运商。"""
    n = num.strip().upper()
    if UPS_RE.fullmatch(n):
        return "UPS"
    if AMAZON_RE.fullmatch(n):
        return "Amazon"
    if USPS_INTL_RE.fullmatch(n) or USPS_NUM_RE.fullmatch(n):
        return "USPS"
    if FEDEX_NUM_RE.fullmatch(n):
        return "FedEx"
    return "Other"


_NOT_DELIVERED = re.compile(
    r"out for delivery|attempt|not delivered|undeliver|will be delivered|"
    r"scheduled|expected|estimated|delivery exception|delivery date|failed|"
    r"rescheduled|delivery address|available for delivery",
    re.I,
)


def is_delivered(status):
    if not status:
        return False
    s = status.lower()
    if _NOT_DELIVERED.search(s):
        return False
    return bool(re.search(r"\bdelivered\b|已签收|已妥投", s))
