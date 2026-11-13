"""Debug helper: track one number in a visible browser and print what the widget would read.
Quit the widget first (both use the same browser profile).

Usage (inside the ParcelWidget folder):
    .venv/bin/python debug_track.py 1Z999AA10123456784                    # visible Chrome
    .venv/bin/python debug_track.py 1Z999AA10123456784 --headless         # like the widget's background mode
    .venv/bin/python debug_track.py 1Z999AA10123456784 --browser firefox  # chrome|msedge|brave|chromium|firefox|webkit
"""
import argparse
import os

from tracker import BROWSERS, DEFAULT_BROWSER, ParcelsAppTracker

ap = argparse.ArgumentParser()
ap.add_argument("number", nargs="?", default="1Z999AA10123456784")
ap.add_argument("--headless", action="store_true")
ap.add_argument("--browser", default=DEFAULT_BROWSER, choices=list(BROWSERS))
a = ap.parse_args()

import instance  # noqa: E402
root = os.path.join(instance.BASE, "browser-profile")
t = ParcelsAppTracker(root, headless=a.headless, browser=a.browser)
t.track_many([a.number], lambda n, r: print("\nResult:", n, r))
