#!/usr/bin/env python3
"""
GitHub Actions watcher: checks District pages and sends ntfy alerts.
Runs once per invocation (the workflow schedules it every 10 minutes).
Topic names come from GitHub secrets, never from this file.
"""
import os, sys, datetime, urllib.request
from playwright.sync_api import sync_playwright

LIVE_WORD = "book tickets"

# baseline = how many times "book tickets" appears on the page while booking is CLOSED.
# Alert fires when the count goes ABOVE it. Use the "baseline=" value your local script printed.
# Set to None to only report the count in the status message (no live alerts).
MOVIES = [
    {
        "name": "Avengers: Doomsday",
        "url": "https://district.in/movies/avengers-doomsday-movie-tickets-MV176735",
        "must": "avengers",
        "baseline": 1,
        "topic_env": "NTFY_TOPIC_DOOMSDAY",
    },
    {
        "name": "Godzilla Minus Zero",
        "url": "https://www.district.in/movies/godzilla-minus-zero-movie-tickets-MV219297",
        "must": "godzilla",
        "baseline": None,          # <-- replace with the number your Godzilla script printed
        "topic_env": "NTFY_TOPIC_GODZILLA",
    },
]


def notify(topic, title, msg, priority="default", click=None):
    if not topic:
        print("no topic set, skipping notify:", title)
        return
    headers = {"Title": title.encode("utf-8"), "Priority": priority}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"), headers=headers)
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print("notify failed:", e)


def main():
    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    heartbeat = manual or (ist.hour % 6 == 0 and ist.minute < 10)   # about every 6 hours
    any_error = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="en-IN", timezone_id="Asia/Kolkata")
        for m in MOVIES:
            topic = os.environ.get(m["topic_env"], "")
            try:
                page.goto(m["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                text = page.inner_text("body").lower()
                if m["must"] not in text:
                    raise RuntimeError("page did not load properly")
                count = text.count(LIVE_WORD)
                base = m["baseline"]
                live = base is not None and count > base
                print(f"{m['name']}: count={count} baseline={base} live={live}")
                if live:
                    notify(topic, f"🎟 {m['name'].upper()} TICKETS LIVE on District!",
                           "Booking looks open. Go book!", "urgent", m["url"])
                elif heartbeat:
                    notify(topic, "Still watching",
                           f"{m['name']}: not live | count={count} baseline={base} | {ist:%H:%M} IST", "low")
            except Exception as e:
                any_error = True
                print(f"{m['name']}: ERROR {e}")
                if heartbeat:
                    notify(topic, "Watcher error", f"{m['name']}: {str(e)[:100]}", "default")
        browser.close()
    sys.exit(1 if any_error else 0)


if __name__ == "__main__":
    main()
