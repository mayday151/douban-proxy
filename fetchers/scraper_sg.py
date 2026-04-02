"""
Scrapers for Singapore event platforms that don't require API keys:
- SISTIC (main SG ticketing platform) — scrapes category pages
- Esplanade (performing arts centre)
- Marina Bay Sands Theatre
"""
import logging
import re
from datetime import datetime, timedelta
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# SISTIC category pages — more reliable than the main listing
SISTIC_CATEGORIES = [
    "https://www.sistic.com.sg/events/concerts",
    "https://www.sistic.com.sg/events/musicals-theatre",
    "https://www.sistic.com.sg/events/family",
    "https://www.sistic.com.sg/events/dance-ballet",
    "https://www.sistic.com.sg/events/classical-music",
    "https://www.sistic.com.sg/events/comedy",
]


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
    seen: set[str] = set()

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for url in SISTIC_CATEGORIES:
            try:
                resp = client.get(url, headers=HEADERS)
                resp.raise_for_status()
            except Exception as e:
                logger.warning("SISTIC %s failed: %s", url, e)
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            cards = _find_cards(soup)
            logger.debug("SISTIC %s: found %d cards", url, len(cards))

            for card in cards:
                ev = _parse_card(card, filter_terms, now, end, seen, "sistic", "https://www.sistic.com.sg")
                if ev:
                    events.append(ev)

    logger.info("Fetched %d events from SISTIC", len(events))
    return events


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
    seen: set[str] = set()

    urls = [
        "https://www.esplanade.com/whats-on",
        "https://www.esplanade.com/whats-on/arts/music",
        "https://www.esplanade.com/whats-on/arts/theatre",
        "https://www.esplanade.com/whats-on/arts/dance",
    ]

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = client.get(url, headers=HEADERS)
                resp.raise_for_status()
            except Exception as e:
                logger.warning("Esplanade %s failed: %s", url, e)
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            cards = _find_cards(soup)
            logger.debug("Esplanade %s: found %d cards", url, len(cards))

            for card in cards:
                ev = _parse_card(card, filter_terms, now, end, seen, "esplanade", "https://www.esplanade.com")
                if ev:
                    ev["venue"] = "Esplanade – Theatres on the Bay"
                    ev["address"] = "1 Esplanade Dr, Singapore 038981"
                    events.append(ev)

    logger.info("Fetched %d events from Esplanade", len(events))
    return events


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _find_cards(soup: BeautifulSoup) -> list:
    """Try a series of selectors to find event cards."""
    for selector in [
        "article",
        ".event-item",
        ".event-card",
        ".event-listing-item",
        ".programme-item",
        ".card",
        "[class*='event']",
        "[class*='programme']",
        "[class*='show']",
    ]:
        cards = soup.select(selector)
        if cards:
            return cards
    return []


def _parse_card(
    card,
    filter_terms: list[str],
    now: datetime,
    end: datetime,
    seen: set,
    source: str,
    base_url: str,
) -> dict | None:
    title_el = card.select_one("h2, h3, h4, [class*='title'], [class*='name']")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title or len(title) < 3 or title in seen:
        return None

    desc_el = card.select_one("p, [class*='desc'], [class*='summary'], [class*='excerpt']")
    desc = desc_el.get_text(strip=True) if desc_el else ""
    combined = (title + " " + desc).lower()

    # Apply keyword filter (skip if no filter terms — accept all)
    if filter_terms and not any(t in combined for t in filter_terms):
        return None

    seen.add(title)

    date_el = card.select_one("time, [class*='date'], [class*='when']")
    date_text = ""
    if date_el:
        date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
    start_dt = _parse_sg_date(date_text) or now

    if start_dt > end:
        return None

    link_el = card.select_one("a[href]")
    href = link_el["href"] if link_el else ""
    if href and not href.startswith("http"):
        href = base_url + href
    url = href or base_url

    venue_el = card.select_one("[class*='venue'], [class*='location'], [class*='place']")
    venue = venue_el.get_text(strip=True) if venue_el else "Singapore"

    return {
        "id": f"{source}-{re.sub(r'[^a-z0-9]', '-', title.lower())[:50]}",
        "title": title,
        "start_dt": start_dt,
        "end_dt": None,
        "description": f"{desc}\n\nMore info: {url}".strip(),
        "url": url,
        "venue": venue,
        "address": "Singapore",
        "type": "event",
        "source": source,
    }


# ---------------------------------------------------------------------------
# Date parser
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
    try:
        return datetime.fromisoformat(text).astimezone(SG_TZ)
    except Exception:
        return None
