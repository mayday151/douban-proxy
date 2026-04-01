"""
Fetch concerts and musicals in Singapore from Ticketmaster Discovery API.
Free API key at: https://developer.ticketmaster.com/
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

SG_TZ = timezone(timedelta(hours=8))
TM_BASE = "https://app.ticketmaster.com/discovery/v2"

# Ticketmaster segment/classification IDs
TM_SEGMENTS = {
    "music": "KZFzniwnSyZfZ7v7nJ",   # Music
    "arts": "KZFzniwnSyZfZ7v7na",    # Arts & Theatre
}

TM_GENRES = {
    "concert": "KnvZfZ7vAeA",        # Rock (catch-all for concerts)
    "pop": "KnvZfZ7vAev",
    "classical": "KnvZfZ7vAeJ",
    "musical": "KnvZfZ7v7lv",        # Musical theatre
    "theatre": "KnvZfZ7v7lt",
    "ballet": "KnvZfZ7v7l1",
    "opera": "KnvZfZ7v7lE",
    "comedy": "KnvZfZ7vAe1",
}


def fetch_ticketmaster_events(
    api_key: str,
    categories: list[str],
    keywords: list[str],
    lookahead_days: int,
) -> list[dict]:
    if not api_key or api_key == "YOUR_TICKETMASTER_API_KEY":
        logger.warning("No Ticketmaster API key configured, skipping")
        return []

    now = datetime.now(SG_TZ)
    end = now + timedelta(days=lookahead_days)

    events = []
    seen_ids = set()

    # Map user config categories to TM segment IDs
    segment_ids = []
    if any(c in categories for c in ["music", "concert"]):
        segment_ids.append(TM_SEGMENTS["music"])
    if any(c in categories for c in ["arts", "theatre", "musical"]):
        segment_ids.append(TM_SEGMENTS["arts"])

    search_terms = keywords if keywords else [""]

    with httpx.Client(timeout=20) as client:
        for term in search_terms:
            params = {
                "apikey": api_key,
                "countryCode": "SG",
                "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size": 50,
                "sort": "date,asc",
            }
            if term:
                params["keyword"] = term
            if segment_ids:
                params["segmentId"] = ",".join(segment_ids)

            page = 0
            while True:
                params["page"] = page
                try:
                    resp = client.get(f"{TM_BASE}/events.json", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.warning("Ticketmaster fetch failed for '%s': %s", term, e)
                    break

                embedded = data.get("_embedded", {})
                tm_events = embedded.get("events", [])
                if not tm_events:
                    break

                for ev in tm_events:
                    eid = ev.get("id", "")
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)

                    name = ev.get("name", "Untitled")
                    dates = ev.get("dates", {})
                    start = dates.get("start", {})
                    date_str = start.get("localDate", "")
                    time_str = start.get("localTime", "20:00:00")

                    if not date_str:
                        continue

                    try:
                        from zoneinfo import ZoneInfo
                        sg_tz = ZoneInfo("Asia/Singapore")
                        start_dt = datetime.fromisoformat(f"{date_str}T{time_str}").replace(tzinfo=sg_tz)
                    except Exception:
                        continue

                    # Venue
                    venues = ev.get("_embedded", {}).get("venues", [{}])
                    venue = venues[0] if venues else {}
                    venue_name = venue.get("name", "")
                    venue_address = venue.get("address", {}).get("line1", "Singapore")

                    # Price range
                    price_ranges = ev.get("priceRanges", [])
                    price_str = ""
                    if price_ranges:
                        pr = price_ranges[0]
                        mn = pr.get("min", "")
                        mx = pr.get("max", "")
                        currency = pr.get("currency", "SGD")
                        if mn and mx:
                            price_str = f"\nPrice: {currency} {mn:.0f}–{mx:.0f}"
                        elif mn:
                            price_str = f"\nPrice: from {currency} {mn:.0f}"

                    # Classification label
                    classifications = ev.get("classifications", [{}])
                    segment_name = classifications[0].get("segment", {}).get("name", "")
                    genre_name = classifications[0].get("genre", {}).get("name", "")

                    url = ev.get("url", "")
                    description = f"Venue: {venue_name}\n{venue_address}{price_str}\n\nTickets: {url}"

                    events.append({
                        "id": f"ticketmaster-{eid}",
                        "title": name,
                        "start_dt": start_dt,
                        "end_dt": None,
                        "description": description,
                        "url": url,
                        "venue": venue_name,
                        "address": venue_address or "Singapore",
                        "type": "event",
                        "source": "ticketmaster",
                        "label": f"{segment_name} / {genre_name}".strip(" /"),
                    })

                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 1)
                if page >= total_pages - 1:
                    break
                page += 1

    logger.info("Fetched %d events from Ticketmaster SG", len(events))
    return events
