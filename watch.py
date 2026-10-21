#!/usr/bin/env python3
"""
GitHub Actions watcher (no baseline).
Every run, for each movie:
  - page blocked      -> quiet status "BLOCKED"
  - "Book Tickets" visible on the page -> URGENT alert
  - otherwise         -> quiet status "not live"
Topic names come from GitHub secrets.
"""
import os, re, sys, datetime, urllib.request
from playwright.sync_api import sync_playwright

MOVIES = [
    {
        "name": "Avengers: Doomsday",
        "url": "https://www.district.in/movies/avengers-doomsday-movie-tickets-MV176735",
        "title_word": "doomsday",
        "topic_env": "NTFY_TOPIC_DOOMSDAY",
    },
    {
        "name": "Godzilla Minus Zero",
        "url": "https://www.district.in/movies/godzilla-minus-zero-movie-tickets-MV219297",
        "title_word": "godzilla",
        "topic_env": "NTFY_TOPIC_GODZILLA",
    },
]

BOOK_BUTTON = re.compile(r"^\s*book tickets\s*$", re.I)


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


def visible_book_buttons(page):
    n = 0
    for el in page.get_by_text(BOOK_BUTTON).all():
        try:
            if el.is_visible():
                n += 1
        except Exception:
            pass
    return n


def main():
    ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    stamp = f"{ist:%H:%M} IST"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="en-IN", timezone_id="Asia/Kolkata")
        for m in MOVIES:
            topic = os.environ.get(m["topic_env"], "")
            try:
                page.goto(m["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                text = page.inner_text("body").lower()

                if "access denied" in text or m["title_word"] not in text:
                    print(f"{m['name']}: BLOCKED or not loaded")
                    notify(topic, "Status: BLOCKED",
                           f"{m['name']}: District did not return the page (Access Denied). {stamp}", "low")
                    continue

                if visible_book_buttons(page) > 0:
                    print(f"{m['name']}: LIVE")
                    notify(topic, f"🎟 {m['name'].upper()} TICKETS LIVE on District!",
                           "'Book Tickets' is showing. Go book!", "urgent", m["url"])
                else:
                    print(f"{m['name']}: not live")
                    notify(topic, "Status: not live", f"{m['name']}: not live yet. {stamp}", "low")
            except Exception as e:
                print(f"{m['name']}: ERROR {e}")
                notify(topic, "Status: ERROR", f"{m['name']}: {str(e)[:100]} ({stamp})", "low")
        browser.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
