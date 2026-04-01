"""
Fetch concerts, performances and events in Singapore.

Sources:
  1. Eventbrite API (requires free API key)
  2. SISTIC scraper (fallback, no key needed)
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SG_TZ = timezone(timedelta(hours=8))

# Eventbrite category IDs
EVENTBRITE_CATEGORIES = {
    "music": "103",
    "arts": "105",
    "film": "104",
    "food": "110",
    "sports": "108",
    "comedy": "113",
    "theatre": "105",  # arts & theatre share category
    "dance": "105",
}


# ---------------------------------------------------------------------------
# Eventbrite
# ---------------------------------------------------------------------------

def fetch_eventbrite_events(
    api_key: str,
    categories: list[str],
    keywords: list[str],
    tracked_venues: list[str],
    max_price_sgd: float,
    lookahead_days: int,
) -> list[dict]:
    if not api_key or api_key == "YOUR_EVENTBRITE_API_KEY":
        logger.warning("No Eventbrite API key configured, skipping Eventbrite fetch")
        return []

    now = datetime.now(SG_TZ)
    end = now + timedelta(days=lookahead_days)
    category_ids = list({EVENTBRITE_CATEGORIES[c] for c in categories if c in EVENTBRITE_CATEGORIES})

    events = []
    seen_ids = set()

    # Search by keyword
    search_terms = keywords + tracked_venues
    with httpx.Client(timeout=15) as client:
        for term in search_terms:
            page = 1
            while True:
                try:
                    resp = client.get(
                        "https://www.eventbriteapi.com/v3/events/search/",
                        params={
                            "token": api_key,
                            "q": term,
                            "location.address": "Singapore",
                            "location.within": "10km",
                            "start_date.range_start": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "start_date.range_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "categories": ",".join(category_ids),
                            "expand": "venue",
                            "page": page,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("Eventbrite fetch failed for '%s': %s", term, e)
                    break

                for ev in data.get("events", []):
                    eid = ev["id"]
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)

                    start = ev.get("start", {})
                    end_time = ev.get("end", {})
                    start_dt = _parse_dt(start.get("local", ""), start.get("timezone", "Asia/Singapore"))
                    end_dt = _parse_dt(end_time.get("local", ""), end_time.get("timezone", "Asia/Singapore"))
                    if not start_dt:
                        continue

                    venue = ev.get("venue", {}) or {}
                    events.append({
                        "id": f"eventbrite-{eid}",
                        "title": ev.get("name", {}).get("text", "Untitled Event"),
                        "start_dt": start_dt,
                        "end_dt": end_dt,
                        "description": ev.get("description", {}).get("text", ""),
                        "url": ev.get("url", ""),
                        "venue": venue.get("name", ""),
                        "address": venue.get("address", {}).get("localized_address_display", "Singapore"),
                        "type": "event",
                        "source": "eventbrite",
                    })

                pagination = data.get("pagination", {})
                if page >= pagination.get("page_count", 1):
                    break
                page += 1

    logger.info("Fetched %d events from Eventbrite", len(events))
    return events


# ---------------------------------------------------------------------------
# SISTIC scraper (no API key needed)
# ---------------------------------------------------------------------------

def fetch_sistic_events(
    keywords: list[str],
    tracked_venues: list[str],
    lookahead_days: int,
) -> list[dict]:
    """
    Scrapes SISTIC's What's On page for upcoming events in Singapore.
    Filters by keywords or tracked venues.
    """
    events = []
    seen_titles = set()
    now = datetime.now(SG_TZ)
    end = now + timedelta(days=lookahead_days)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            resp = client.get("https://www.sistic.com.sg/events", headers=headers)
            resp.raise_for_status()
    except Exception as e:
        logger.warning("SISTIC fetch failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # SISTIC event cards
    cards = soup.select(".event-listing-item, .event-card, article.event")
    if not cards:
        # Broader fallback selector
        cards = soup.select("[class*='event']")

    filter_terms = [kw.lower() for kw in keywords + tracked_venues]

    for card in cards:
        title_el = card.select_one("h2, h3, .event-title, .title")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or title in seen_titles:
            continue

        # Apply keyword filter
        title_lower = title.lower()
        desc_el = card.select_one(".description, .event-desc, p")
        desc_text = desc_el.get_text(strip=True) if desc_el else ""
        combined = title_lower + " " + desc_text.lower()

        if filter_terms and not any(term in combined for term in filter_terms):
            continue

        seen_titles.add(title)

        # Try to parse date
        date_el = card.select_one(".date, .event-date, time")
        date_text = date_el.get_text(strip=True) if date_el else ""
        start_dt = _parse_sistic_date(date_text, now)

        if start_dt and start_dt > end:
            continue

        link_el = card.select_one("a[href]")
        url = ""
        if link_el:
            href = link_el["href"]
            url = href if href.startswith("http") else f"https://www.sistic.com.sg{href}"

        venue_el = card.select_one(".venue, .event-venue")
        venue = venue_el.get_text(strip=True) if venue_el else "Singapore"

        events.append({
            "id": f"sistic-{re.sub(r'[^a-z0-9]', '-', title.lower()[:40])}",
            "title": title,
            "start_dt": start_dt or now,
            "end_dt": None,
            "description": desc_text or f"Event in Singapore. More info: {url}",
            "url": url,
            "venue": venue,
            "address": "Singapore",
            "type": "event",
            "source": "sistic",
        })

    logger.info("Fetched %d events from SISTIC", len(events))
    return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(local_str: str, tz_name: str) -> datetime | None:
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.fromisoformat(local_str)
        return dt.replace(tzinfo=ZoneInfo(tz_name or "Asia/Singapore"))
    except Exception:
        return None


def _parse_sistic_date(text: str, fallback: datetime) -> datetime | None:
    """Best-effort parse of informal date strings from SISTIC."""
    if not text:
        return None
    # Try common formats
    formats = [
        "%d %b %Y",
        "%d %B %Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%b %d, %Y",
    ]
    text = re.sub(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s*", "", text).strip()
    # Extract first date-looking substring
    match = re.search(r"\d{1,2}[\s/\-]\w+[\s/\-]\d{4}", text)
    if match:
        text = match.group(0)
    for fmt in formats:
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=SG_TZ)
        except ValueError:
            continue
    return None
