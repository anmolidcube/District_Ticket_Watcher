
#!/usr/bin/env python3
"""
District movie ticket watcher for GitHub Actions.

For each movie:
  - BLOCKED: Access denied, bot challenge, or HTTP restriction.
  - PAGE NOT VERIFIED: Page loaded, but the expected movie title was not found.
  - LIVE: A visible booking button/link was detected.
  - NOT LIVE: Movie page verified, but no booking control was detected.
  - ERROR: Navigation or page inspection failed.

Notifications are sent through ntfy.sh using GitHub Secrets.

Required GitHub Secrets:
  NTFY_TOPIC_DOOMSDAY
  NTFY_TOPIC_GODZILLA
"""

import os
import re
import sys
import datetime
import urllib.request
import urllib.error

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


MOVIES = [
    {
        "name": "Avengers: Doomsday",
        "url": "https://district.in/movies/avengers-doomsday-movie-tickets-MV176735",
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

BOOKING_PATTERN = re.compile(
    r"\b(book\s*tickets?|book\s*now|buy\s*tickets?|get\s*tickets?)\b",
    re.IGNORECASE,
)

BLOCKED_PHRASES = (
    "access denied",
    "verify you are human",
    "unusual traffic",
    "security check",
    "captcha",
    "request blocked",
    "temporarily blocked",
)

# Set DEBUG_HTML=1 in GitHub Actions to print a larger body preview.
BODY_PREVIEW_LENGTH = 1200 if os.getenv("DEBUG_HTML") == "1" else 400


def timestamp_ist():
    """Return the current time in India Standard Time."""
    now = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    )
    return now.strftime("%Y-%m-%d %H:%M:%S IST")


def notify(topic, title, message, priority="default", click=None):
    """Send an ntfy notification. Never print the secret topic."""
    if not topic:
        print("Notification skipped: required topic secret is missing.")
        return False

    headers = {
        "Title": title,
        "Priority": priority,
        "Tags": "movie",
    }

    if click:
        headers["Click"] = click

    request = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(f"Notification sent (HTTP {response.status}).")
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Notification failed: {type(exc).__name__}: {exc}")
        return False


def inspect_booking_controls(page):
    """
    Search visible buttons, links, and role=button elements.

    Returns a matching label or None.
    """
    selectors = [
        "button",
        "a",
        '[role="button"]',
    ]

    for selector in selectors:
        elements = page.locator(selector)

        try:
            count = min(elements.count(), 300)
        except Exception:
            continue

        for index in range(count):
            element = elements.nth(index)

            try:
                if not element.is_visible(timeout=1000):
                    continue

                label = (
                    element.inner_text(timeout=1500)
                    or element.get_attribute("aria-label")
                    or element.get_attribute("title")
                    or ""
                ).strip()

                if BOOKING_PATTERN.search(label):
                    return " ".join(label.split())[:160]

            except Exception:
                continue

    # Fallback: inspect exact text nodes and their visibility.
    try:
        matches = page.get_by_text(
            re.compile(r"^\s*book\s*tickets?\s*$", re.IGNORECASE)
        )

        for index in range(min(matches.count(), 50)):
            element = matches.nth(index)
            try:
                if element.is_visible(timeout=1000):
                    return "Book Tickets"
            except Exception:
                continue
    except Exception:
        pass

    return None


def inspect_movie(page, movie):
    """
    Navigate to the movie page and return:
      (status, details, booking_label)
    """
    response = page.goto(
        movie["url"],
        wait_until="domcontentloaded",
        timeout=45000,
    )

    # Allow client-rendered content to appear.
    try:
        page.wait_for_load_state("load", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(4000)

    http_status = response.status if response else None
    final_url = page.url

    try:
        page_title = page.title()
    except Exception:
        page_title = "(unavailable)"

    try:
        body_text = page.locator("body").inner_text(timeout=10000).lower()
    except Exception:
        body_text = ""

    print(f"HTTP status: {http_status}")
    print(f"Page title: {page_title}")
    print(f"Final URL: {final_url}")
    print(
        f"Body preview: "
        f"{body_text[:BODY_PREVIEW_LENGTH]!r}"
    )

    details = (
        f"Checked: {timestamp_ist()}\n"
        f"HTTP status: {http_status}\n"
        f"Page title: {page_title}\n"
        f"URL: {final_url}"
    )

    # HTTP-level access restrictions.
    if http_status in (401, 403, 429):
        return "BLOCKED", details, None

    # Look for explicit challenge/access-denial text.
    if any(phrase in body_text for phrase in BLOCKED_PHRASES):
        return "BLOCKED", details, None

    # A missing response or server error is not a confirmed availability result.
    if http_status is None or http_status >= 500:
        return "ERROR", details, None

    # Verify that the expected movie page actually loaded.
    if movie["title_word"] not in body_text:
        return "PAGE NOT VERIFIED", details, None

    # Check for a real, visible booking control.
    booking_label = inspect_booking_controls(page)

    if booking_label:
        return "LIVE", details, booking_label

    return "NOT LIVE", details, None


def main():
    print("=" * 60)
    print("District movie watcher")
    print(f"Run time: {timestamp_ist()}")
    print("=" * 60)

    failures = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        context = browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={"width": 1365, "height": 900},
        )

        page = context.new_page()
        page.set_default_timeout(10000)

        for movie in MOVIES:
            print(f"\n--- {movie['name']} ---")
            topic = os.environ.get(movie["topic_env"], "").strip()

            try:
                status, details, booking_label = inspect_movie(page, movie)

                print(f"Result: {status}")

                if status == "LIVE":
                    message = (
                        f"{movie['name']} appears to have a booking control.\n"
                        f"Detected label: {booking_label}\n"
                        f"{details}\n"
                        f"Open: {movie['url']}"
                    )

                    notify(
                        topic,
                        f"🎟 {movie['name'].upper()} TICKETS LIVE!",
                        message,
                        priority="urgent",
                        click=movie["url"],
                    )

                elif status == "BLOCKED":
                    failures += 1
                    notify(
                        topic,
                        f"⚠️ {movie['name']}: PAGE BLOCKED",
                        f"District access may be restricted.\n{details}",
                        priority="low",
                        click=movie["url"],
                    )

                elif status == "PAGE NOT VERIFIED":
                    failures += 1
                    notify(
                        topic,
                        f"⚠️ {movie['name']}: PAGE NOT VERIFIED",
                        f"The expected movie title was not found.\n{details}",
                        priority="low",
                        click=movie["url"],
                    )

                elif status == "NOT LIVE":
                    print("No visible booking control detected.")
                    notify(
                        topic,
                        f"{movie['name']}: Not live",
                        f"No visible booking control was detected.\n{details}",
                        priority="low",
                        click=movie["url"],
                    )

                else:
                    failures += 1
                    notify(
                        topic,
                        f"⚠️ {movie['name']}: CHECK FAILED",
                        f"Could not verify ticket availability.\n{details}",
                        priority="low",
                        click=movie["url"],
                    )

            except Exception as exc:
                failures += 1
                error_message = f"{type(exc).__name__}: {str(exc)[:300]}"
                print(f"ERROR: {error_message}")

                notify(
                    topic,
                    f"⚠️ {movie['name']}: WATCHER ERROR",
                    f"{error_message}\nChecked: {timestamp_ist()}",
                    priority="low",
                    click=movie["url"],
                )

        context.close()
        browser.close()

    print("\nWatcher finished.")

    # Make failed checks visible to GitHub Actions.
    if failures:
        print(f"::warning::{failures} movie check(s) could not be verified.")

    # Keep exit code 0 so expected blocking/challenges don't break the schedule.
    sys.exit(0)


if __name__ == "__main__":
    main()
