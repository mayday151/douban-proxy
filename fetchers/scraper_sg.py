"""
Scrapers for Singapore event platforms that don't require API keys:
- SISTIC (main SG ticketing platform)
- Esplanade (performing arts centre)
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SG_TZ = ZoneInfo("Asia/Singapore")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# SISTIC
# ---------------------------------------------------------------------------

def fetch_sistic_events(
    keywords: list[str],
    tracked_venues: list[str],
    lookahead_days: int,
) -> list[dict]:
    events = []
    filter_terms = [t.lower() for t in keywords + tracked_venues]
    now = datetime.now(SG_TZ)
    end = now + timedelta(days=lookahead_days)

    # SISTIC uses paginated event listing
    page = 1
    seen = set()

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        while page <= 5:
            try:
                resp = client.get(
                    "https://www.sistic.com.sg/events",
                    params={"page": page},
                    headers=HEADERS,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.warning("SISTIC page %d failed: %s", page, e)
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Try multiple card selectors across SISTIC's layouts
            cards = (
                soup.select(".event-item") or
                soup.select(".event-listing-item") or
                soup.select("article[class*='event']") or
                soup.select(".card-event") or
                soup.select("[data-event-id]")
            )

            if not cards:
                break

            new_this_page = 0
            for card in cards:
                ev = _parse_sistic_card(card, filter_terms, now, end, seen)
                if ev:
                    events.append(ev)
                    new_this_page += 1

            if new_this_page == 0:
                break
            page += 1

    logger.info("Fetched %d events from SISTIC", len(events))
    return events


def _parse_sistic_card(
    card, filter_terms: list[str], now: datetime, end: datetime, seen: set
) -> dict | None:
    title_el = card.select_one("h2, h3, h4, .event-title, .title, [class*='title']")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title or title in seen:
        return None

    desc_el = card.select_one(".description, .summary, p")
    desc = desc_el.get_text(strip=True) if desc_el else ""
    combined = (title + " " + desc).lower()

    if filter_terms and not any(t in combined for t in filter_terms):
        return None

    seen.add(title)

    date_el = card.select_one("time, .date, .event-date, [class*='date']")
    date_text = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
    start_dt = _parse_sg_date(date_text) or now

    if start_dt > end:
        return None

    link_el = card.select_one("a[href]")
    href = link_el["href"] if link_el else ""
    url = href if href.startswith("http") else f"https://www.sistic.com.sg{href}"

    venue_el = card.select_one(".venue, [class*='venue'], .location")
    venue = venue_el.get_text(strip=True) if venue_el else "Singapore"

    return {
        "id": f"sistic-{re.sub(r'[^a-z0-9]', '-', title.lower())[:50]}",
        "title": title,
        "start_dt": start_dt,
        "end_dt": None,
        "description": f"{desc}\n\nMore info: {url}".strip(),
        "url": url,
        "venue": venue,
        "address": "Singapore",
        "type": "event",
        "source": "sistic",
    }


# ---------------------------------------------------------------------------
# Esplanade
# ---------------------------------------------------------------------------

def fetch_esplanade_events(
    keywords: list[str],
    lookahead_days: int,
) -> list[dict]:
    events = []
    filter_terms = [t.lower() for t in keywords] if keywords else []
    now = datetime.now(SG_TZ)
    end = now + timedelta(days=lookahead_days)
    seen = set()

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        try:
            resp = client.get(
                "https://www.esplanade.com/whats-on",
                headers=HEADERS,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Esplanade fetch failed: %s", e)
            return []

    soup = BeautifulSoup(resp.text, "lxml")

    cards = (
        soup.select(".event-card") or
        soup.select(".programme-item") or
        soup.select("article") or
        soup.select("[class*='event']")
    )

    for card in cards:
        title_el = card.select_one("h2, h3, h4, .title, [class*='title']")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or title in seen:
            continue

        desc_el = card.select_one("p, .description, .summary")
        desc = desc_el.get_text(strip=True) if desc_el else ""
        combined = (title + " " + desc).lower()

        if filter_terms and not any(t in combined for t in filter_terms):
            continue

        seen.add(title)

        date_el = card.select_one("time, .date, [class*='date']")
        date_text = date_el.get("datetime", "") or (date_el.get_text(strip=True) if date_el else "")
        start_dt = _parse_sg_date(date_text) or now

        if start_dt > end:
            continue

        link_el = card.select_one("a[href]")
        href = link_el["href"] if link_el else ""
        url = href if href.startswith("http") else f"https://www.esplanade.com{href}"

        events.append({
            "id": f"esplanade-{re.sub(r'[^a-z0-9]', '-', title.lower())[:50]}",
            "title": title,
            "start_dt": start_dt,
            "end_dt": None,
            "description": f"{desc}\n\nMore info: {url}".strip(),
            "url": url,
            "venue": "Esplanade – Theatres on the Bay",
            "address": "1 Esplanade Dr, Singapore 038981",
            "type": "event",
            "source": "esplanade",
        })

    logger.info("Fetched %d events from Esplanade", len(events))
    return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sg_date(text: str) -> datetime | None:
    if not text:
        return None
    text = re.sub(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[,.]?\s*", "", text, flags=re.I).strip()
    match = re.search(r"\d{1,2}[\s\-/]\w+[\s\-/]\d{2,4}", text)
    if match:
        text = match.group(0)
    for fmt in ("%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d/%m/%Y",
                "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %y"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=SG_TZ)
        except ValueError:
            continue
    # ISO datetime
    try:
        return datetime.fromisoformat(text).astimezone(SG_TZ)
    except Exception:
        return None
