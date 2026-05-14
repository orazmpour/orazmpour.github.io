#!/usr/bin/env python3
"""
Modera Reynoldstown Apartment Availability Monitor.

Scrapes the Modera Reynoldstown availability page twice daily, filters for
7th-floor 2-bed and 3-bed units, and emails the configured recipients.

Designed to be run by cron at 9 AM and 5 PM US/Eastern.

Files (all live next to this script):
  - config.json      Email credentials and recipient list
  - state.json       Units already notified (so we only re-mail on changes)
  - monitor.log      Rolling log of every run
"""

from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import sys
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
STATE_PATH = SCRIPT_DIR / "state.json"
LOG_PATH = SCRIPT_DIR / "monitor.log"

LISTINGS_URL = (
    "https://www.moderareynoldstown.com/atlanta/modera-reynoldstown/conventional/"
)

# The Modera site is built on the Entrata "Prospect Portal". The browser-visible
# table is hydrated from a JSON endpoint. We try the JSON endpoint first because
# it is stable and cheap; if it ever changes we fall back to HTML scraping.
ENTRATA_AVAILABILITY_URL = (
    "https://www.moderareynoldstown.com/api/v1/properties/"
    "modera-reynoldstown/availability"
)

REQUEST_TIMEOUT = 30  # seconds
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Filters
TARGET_FLOOR = 7
TARGET_BEDROOMS = {2, 3}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
# Also echo to stdout so manual runs show output in the terminal.
_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(_console)
log = logging.getLogger("apartment_monitor")


# ---------------------------------------------------------------------------
# Config + state helpers
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Read config.json and validate the required keys are present."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Missing config file at {CONFIG_PATH}. "
            "Copy config.json template and fill in your Gmail credentials."
        )
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    for key in ("gmail_email", "gmail_app_password", "recipient_emails"):
        if not cfg.get(key):
            raise ValueError(f"config.json is missing required field: {key}")
    if not isinstance(cfg["recipient_emails"], list):
        raise ValueError("config.json 'recipient_emails' must be a list of strings")
    return cfg


def load_state() -> dict[str, Any]:
    """Read state.json. Treat a missing or unreadable file as empty state."""
    if not STATE_PATH.exists():
        return {"notified_units": []}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"notified_units": []}
        data.setdefault("notified_units", [])
        return data
    except json.JSONDecodeError:
        log.warning("state.json was not valid JSON; resetting to empty.")
        return {"notified_units": []}


def save_state(state: dict[str, Any]) -> None:
    """Write state.json atomically so an interrupted write can't corrupt it."""
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    tmp.replace(STATE_PATH)


# ---------------------------------------------------------------------------
# Listing fetch + parsing
# ---------------------------------------------------------------------------


def _normalize_unit(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw API row into our internal unit dict, or None if invalid."""
    # Different Entrata builds use different field names; check both.
    unit_number = (
        raw.get("unitNumber")
        or raw.get("unit_number")
        or raw.get("unit")
        or raw.get("UnitNumber")
    )
    bedrooms = (
        raw.get("bedrooms")
        or raw.get("beds")
        or raw.get("Bedrooms")
        or raw.get("bedroomCount")
    )
    rent = (
        raw.get("rent")
        or raw.get("price")
        or raw.get("startingRent")
        or raw.get("minRent")
    )
    floor = raw.get("floor") or raw.get("Floor") or raw.get("floorNumber")
    available = (
        raw.get("availableDate")
        or raw.get("available_date")
        or raw.get("dateAvailable")
        or raw.get("availability")
    )
    url = raw.get("url") or raw.get("detailUrl") or raw.get("link")

    if unit_number is None or bedrooms is None:
        return None

    try:
        bedrooms = int(bedrooms)
    except (TypeError, ValueError):
        return None

    # If floor wasn't returned, infer it from the unit number (Modera uses the
    # leading digit of a 3- or 4-digit unit number to indicate floor — e.g.
    # 712 = floor 7, 1207 = floor 12).
    if floor is None:
        digits = re.sub(r"\D", "", str(unit_number))
        if len(digits) >= 3:
            floor = int(digits[:-2])
    try:
        floor = int(floor) if floor is not None else None
    except (TypeError, ValueError):
        floor = None

    return {
        "unit": str(unit_number),
        "bedrooms": bedrooms,
        "floor": floor,
        "rent": str(rent) if rent is not None else "N/A",
        "available": str(available) if available else "N/A",
        "url": url or LISTINGS_URL,
    }


def _fetch_via_api(session: requests.Session) -> list[dict[str, Any]]:
    """Try the JSON availability endpoint. Returns [] if it doesn't respond."""
    try:
        resp = session.get(ENTRATA_AVAILABILITY_URL, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        log.info("API endpoint unreachable (%s); will fall back to HTML.", e)
        return []
    if resp.status_code != 200 or "json" not in resp.headers.get("content-type", ""):
        log.info(
            "API endpoint returned status=%s content-type=%s; falling back to HTML.",
            resp.status_code,
            resp.headers.get("content-type"),
        )
        return []
    try:
        payload = resp.json()
    except ValueError:
        return []

    # The payload is typically {"units": [...]} or a bare list.
    rows = payload.get("units") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    units = [u for u in (_normalize_unit(r) for r in rows) if u is not None]
    log.info("Fetched %d units via API.", len(units))
    return units


def _fetch_via_html(session: requests.Session) -> list[dict[str, Any]]:
    """Scrape the public listings page when the JSON endpoint is unavailable."""
    resp = session.get(LISTINGS_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Modera renders results inside table rows tagged with data-* attributes.
    units: list[dict[str, Any]] = []
    for row in soup.select("tr[data-unit], li[data-unit], div[data-unit]"):
        raw = {
            "unitNumber": row.get("data-unit"),
            "bedrooms": row.get("data-beds") or row.get("data-bedrooms"),
            "rent": row.get("data-rent") or row.get("data-price"),
            "floor": row.get("data-floor"),
            "availableDate": row.get("data-available"),
        }
        link = row.find("a", href=True)
        if link:
            raw["url"] = link["href"]
        normalized = _normalize_unit(raw)
        if normalized:
            units.append(normalized)

    # Fallback parser: look for embedded JSON inside <script> tags. Many SPA
    # builds inline the availability list this way.
    if not units:
        for script in soup.find_all("script"):
            text = script.string or ""
            match = re.search(r"availability\s*[:=]\s*(\[.+?\])", text, re.DOTALL)
            if match:
                try:
                    rows = json.loads(match.group(1))
                except ValueError:
                    continue
                for r in rows:
                    n = _normalize_unit(r)
                    if n:
                        units.append(n)
                if units:
                    break

    log.info("Fetched %d units via HTML scrape.", len(units))
    return units


def fetch_listings() -> list[dict[str, Any]]:
    """Return a list of normalized unit dicts available right now."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    units = _fetch_via_api(session)
    if not units:
        units = _fetch_via_html(session)
    return units


def filter_units(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only 7th-floor 2-bed or 3-bed units."""
    matching = [
        u
        for u in units
        if u.get("floor") == TARGET_FLOOR and u.get("bedrooms") in TARGET_BEDROOMS
    ]
    log.info(
        "Filtered to %d matching units (floor=%d, bedrooms in %s).",
        len(matching),
        TARGET_FLOOR,
        sorted(TARGET_BEDROOMS),
    )
    return matching


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def _format_unit_html(unit: dict[str, Any]) -> str:
    return (
        f"<li><strong>Unit {unit['unit']}</strong> — "
        f"{unit['bedrooms']} bed · floor {unit['floor']} · "
        f"rent {unit['rent']} · available {unit['available']} "
        f"(<a href=\"{unit['url']}\">view</a>)</li>"
    )


def _format_unit_text(unit: dict[str, Any]) -> str:
    return (
        f"  - Unit {unit['unit']}: {unit['bedrooms']} bed, floor "
        f"{unit['floor']}, rent {unit['rent']}, available "
        f"{unit['available']}, link: {unit['url']}"
    )


def build_email_body(
    new_units: list[dict[str, Any]],
    all_matching: list[dict[str, Any]],
) -> tuple[str, str, str]:
    """Return (subject, plain_text_body, html_body)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    if new_units:
        subject = (
            f"[Modera Reynoldstown] {len(new_units)} new 7th-floor "
            "2/3-bed unit(s) available"
        )
        text_lines = [
            f"Modera Reynoldstown availability check — {timestamp}",
            "",
            f"NEW units matching your filter (7th floor, 2 or 3 beds): {len(new_units)}",
        ]
        text_lines += [_format_unit_text(u) for u in new_units]
        if len(all_matching) > len(new_units):
            text_lines += [
                "",
                "Other matching units still on the market:",
            ]
            previously = [
                u for u in all_matching if u not in new_units
            ]
            text_lines += [_format_unit_text(u) for u in previously]
        text_lines += ["", f"Source: {LISTINGS_URL}"]
        text_body = "\n".join(text_lines)

        html_body = (
            f"<p>Modera Reynoldstown availability check — {timestamp}</p>"
            f"<p><strong>{len(new_units)} new matching unit(s):</strong></p>"
            f"<ul>{''.join(_format_unit_html(u) for u in new_units)}</ul>"
        )
        previously = [u for u in all_matching if u not in new_units]
        if previously:
            html_body += (
                "<p>Other matching units still listed:</p>"
                f"<ul>{''.join(_format_unit_html(u) for u in previously)}</ul>"
            )
        html_body += f'<p>Source: <a href="{LISTINGS_URL}">{LISTINGS_URL}</a></p>'
    else:
        subject = "[Modera Reynoldstown] No new 7th-floor 2/3-bed units"
        text_body = (
            f"Modera Reynoldstown availability check — {timestamp}\n\n"
            "No new 2 or 3 bed units on 7th floor currently available.\n\n"
            f"Source: {LISTINGS_URL}\n"
        )
        html_body = (
            f"<p>Modera Reynoldstown availability check — {timestamp}</p>"
            "<p>No new 2 or 3 bed units on 7th floor currently available.</p>"
            f'<p>Source: <a href="{LISTINGS_URL}">{LISTINGS_URL}</a></p>'
        )

    return subject, text_body, html_body


def send_email(cfg: dict[str, Any], subject: str, text_body: str, html_body: str) -> None:
    """Send a multipart email via Gmail SMTP with TLS."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["gmail_email"]
    msg["To"] = ", ".join(cfg["recipient_emails"])
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(cfg["gmail_email"], cfg["gmail_app_password"])
        smtp.sendmail(cfg["gmail_email"], cfg["recipient_emails"], msg.as_string())
    log.info("Email sent to: %s", ", ".join(cfg["recipient_emails"]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def unit_key(unit: dict[str, Any]) -> str:
    """Stable identifier for a unit, used for new-vs-seen comparison."""
    return f"{unit['unit']}|{unit['bedrooms']}bd|floor{unit['floor']}"


def run() -> int:
    log.info("=== Apartment monitor run starting ===")
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        log.error("Config error: %s", e)
        return 1

    state = load_state()
    seen_keys: set[str] = set(state.get("notified_units", []))

    try:
        listings = fetch_listings()
    except requests.RequestException as e:
        log.error("Network failure fetching listings: %s", e)
        listings = []
    except Exception as e:  # pragma: no cover - defensive last-resort
        log.error("Unexpected error fetching listings: %s\n%s", e, traceback.format_exc())
        listings = []

    matching = filter_units(listings) if listings else []
    matching_keys = {unit_key(u) for u in matching}
    new_units = [u for u in matching if unit_key(u) not in seen_keys]

    log.info(
        "Matching=%d, previously_notified=%d, new=%d",
        len(matching),
        len(seen_keys),
        len(new_units),
    )

    subject, text_body, html_body = build_email_body(new_units, matching)
    try:
        send_email(cfg, subject, text_body, html_body)
    except (smtplib.SMTPException, OSError) as e:
        log.error("Failed to send email: %s", e)
        return 2

    # Persist the units we just notified about. We replace the whole set with
    # the *currently available* matching units so a unit that disappears and
    # later returns will trigger a fresh notification.
    state["notified_units"] = sorted(matching_keys)
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    save_state(state)

    log.info("=== Apartment monitor run complete ===")
    return 0


if __name__ == "__main__":
    # Make sure cron-launched runs find the script's own directory regardless
    # of the cwd cron uses.
    os.chdir(SCRIPT_DIR)
    sys.exit(run())
