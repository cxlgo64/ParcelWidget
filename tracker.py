"""Open parcelsapp.com in a real browser and read the latest tracking event.

parcelsapp loads its data with signed API calls from page JS, so we drive a real
browser (Playwright) and read the DOM instead of calling the API directly.

Errors are returned as short codes ("blocked", "no_data", "browser_missing:<engine>",
"failed:<detail>") and translated in the UI.
"""
import os
import random
import time

from tracking_parser import is_delivered

URL = "https://parcelsapp.com/en/tracking/{}"

# key -> (engine, launch options). Different browsers look different to anti-bot checks,
# so if one gets blocked, switch to another in Settings.
BROWSERS = {
    "chrome":   ("chromium", {"channel": "chrome"}),          # installed Google Chrome
    "msedge":   ("chromium", {"channel": "msedge"}),          # installed Microsoft Edge
    "brave":    ("chromium", {"executable_path": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"}),
    "chromium": ("chromium", {}),                             # Playwright's bundled Chromium
    "firefox":  ("firefox", {}),                              # Playwright Firefox
    "webkit":   ("webkit", {}),                               # Safari engine
}
DEFAULT_BROWSER = "chrome"

EXTRACT_JS = r"""
() => {
  const events = [...document.querySelectorAll('li.event')].map(li => {
    const t = li.querySelector('.event-time');
    const c = li.querySelector('.event-content');
    return {
      date: t?.querySelector('strong')?.innerText.trim() || '',
      time: t?.querySelector('span')?.innerText.trim() || '',
      status: c?.querySelector('strong')?.innerText.trim() || '',
      location: c?.querySelector('.location')?.innerText.trim() || '',
    };
  });
  const attrs = {};
  document.querySelectorAll('table.parcel-attributes tr').forEach(tr => {
    const tds = tr.querySelectorAll('td');
    if (tds.length >= 2) attrs[tds[0].innerText.trim()] = tds[1].innerText.trim();
  });
  return {events, attrs};
}
"""


def _is_placeholder(status):
    s = (status or "").lower()
    return (not s) or "no information" in s or "not found" in s or "searching" in s or "loading" in s


class BrowserMissing(Exception):
    def __init__(self, engine):
        super().__init__(engine)
        self.engine = engine


class ParcelsAppTracker:
    def __init__(self, profile_root, headless=True, browser=DEFAULT_BROWSER, log=print):
        self.browser = browser if browser in BROWSERS else DEFAULT_BROWSER
        # each browser gets its own profile folder (profiles aren't shareable across engines)
        self.profile_dir = os.path.join(profile_root, self.browser)
        self.headless = headless
        self.log = log
        os.makedirs(self.profile_dir, exist_ok=True)

    def _launch(self, p):
        engine, extra = BROWSERS[self.browser]
        bt = getattr(p, engine)
        opts = dict(headless=self.headless, viewport={"width": 1200, "height": 900}, locale="en-US")
        opts.update(extra)
        if engine == "chromium":
            opts["args"] = ["--disable-blink-features=AutomationControlled"]
            opts["ignore_default_args"] = ["--enable-automation"]
        if "executable_path" in opts and not os.path.exists(opts["executable_path"]):
            raise BrowserMissing(self.browser)
        try:
            ctx = bt.launch_persistent_context(self.profile_dir, **opts)
        except Exception as e:
            msg = str(e)
            if "Executable doesn't exist" in msg or "is not found" in msg or "install" in msg.lower():
                raise BrowserMissing(self.browser)
            raise
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        return ctx

    def track_many(self, numbers, on_result, should_stop=lambda: False, on_start=None):
        """Calls on_start(index, number) before and on_result(number, result_dict) after each number."""
        if not numbers:
            return
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                ctx = self._launch(p)
            except BrowserMissing as e:
                for n in numbers:
                    on_result(n, {"error": "browser_missing:%s" % e.engine})
                return
            try:
                page = ctx.new_page()
                for i, num in enumerate(numbers):
                    if should_stop():
                        break
                    if on_start:
                        on_start(i, num)
                    try:
                        res = self._track_one(page, num)
                    except Exception as e:  # one failure shouldn't stop the rest
                        res = {"error": "failed:%s" % str(e).splitlines()[0][:120]}
                    on_result(num, res)
                    if i < len(numbers) - 1:
                        time.sleep(random.uniform(4, 8))  # be polite
            finally:
                ctx.close()

    def _track_one(self, page, num, attempts=2):
        """parcelsapp first shows a placeholder ("No information…") and swaps in the real
        events once its backend lookup finishes, so poll until real events appear."""
        events, data = [], {}
        for attempt in range(attempts):
            page.goto(URL.format(num), wait_until="domcontentloaded", timeout=45000)
            deadline = time.time() + 60
            while time.time() < deadline:
                page.wait_for_timeout(2000)
                body = page.inner_text("body")[:3000].lower()
                if "captcha" in body or "verify you are human" in body or "just a moment" in body:
                    return {"error": "blocked"}
                data = page.evaluate(EXTRACT_JS)
                events = [e for e in (data.get("events") or []) if not _is_placeholder(e["status"])]
                if events:
                    break
            if events:
                break
            self.log("%s: attempt %d got no real events" % (num, attempt + 1))
        if not events:
            return {"error": "no_data"}
        latest = events[0]
        status = latest["status"]
        return {
            "status": status,
            "location": latest["location"],
            "event_time": (latest["date"] + " " + latest["time"]).strip(),
            "delivered": is_delivered(status),
            "carrier_found": data.get("attrs", {}).get("Found in", ""),
        }
