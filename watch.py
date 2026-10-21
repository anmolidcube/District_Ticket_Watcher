#!/usr/bin/env python3
"""
TEST version: watches a movie that is ALREADY bookable (Drishyam), with the
baseline forced to 0, so the loud "TICKETS LIVE" alert should fire on the first check.
If you get the alert on your phone, detection + notifications both work.

Run:  python ticket_watch_test.py
"""
import time, urllib.request
from playwright.sync_api import sync_playwright

NTFY_TOPIC = "Anmol_Godzilla"      # change to your Doomsday topic if you prefer
URL = "https://district.in/movies/drishyam-the-conclusion-movie-tickets-MV207254"
MOVIE_NAME = "drishyam"
LIVE_WORD = "book tickets"
BASELINE = 0                       # forced to 0 for the test


def notify(title, msg, priority="default", click=None):
    headers = {"Title": title.encode("utf-8"), "Priority": priority}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode("utf-8"), headers=headers)
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print("notify failed:", e)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(locale="en-IN", timezone_id="Asia/Kolkata")
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(5000)
    text = page.inner_text("body").lower()
    if MOVIE_NAME not in text or "access denied" in text:
        print("PAGE DID NOT LOAD PROPERLY (blocked?). First 300 chars:\n", text[:300])
        notify("TEST: page failed to load", "Blocked or not loaded. Detection untested.", "default")
    else:
        count = text.count(LIVE_WORD)
        print(f"count of '{LIVE_WORD}' = {count}, baseline = {BASELINE}")
        if count > BASELINE:
            print("LIVE detected -> sending alerts")
            for _ in range(3):
                notify("🎟 TEST: TICKETS LIVE on District!", "This is a TEST alert (Drishyam). Detection works!", "urgent", URL)
                time.sleep(30)
        else:
            print("NOT detected: count is not above baseline. Detection needs fixing.")
            notify("TEST: not detected", f"count={count}. Button text may differ.", "default")
    browser.close()
