"""
Fetch artist concerts in Singapore via Bandsintown API (free, no key needed).

Usage: add artist names to config.yaml under events.artists
API docs: https://rest.bandsintown.com
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

SG_TZ = ZoneInfo("Asia/Singapore")
BIT_BASE = "https://rest.bandsintown.com/artists"
APP_ID = "sg-events-calendar"  # any string works for public endpoint


def fetch_artist_concerts(
    artists: list[str],
    lookahead_days: int,
) -> list[dict]:
    """
    For each artist, fetch upcoming concerts in or near Singapore.
    Returns event dicts compatible with calendar_builder.
    """
    if not artists:
        return []

    now = datetime.now(SG_TZ)
    end = now + timedelta(days=lookahead_days)
    events = []
    seen_ids = set()

    with httpx.Client(timeout=15) as client:
        for artist in artists:
            try:
                resp = client.get(
                    f"{BIT_BASE}/{_encode(artist)}/events",
                    params={
                        "app_id": APP_ID,
                        "date": f"{now.strftime('%Y-%m-%d')},{end.strftime('%Y-%m-%d')}",
                    },
                )
                if resp.status_code == 404:
                    logger.debug("Artist not found on Bandsintown: %s", artist)
                    continue
                resp.raise_for_status()
                raw = resp.json()
                if not isinstance(raw, list):
                    continue
            except Exception as e:
                logger.warning("Bandsintown fetch failed for '%s': %s", artist, e)
                continue

            for ev in raw:
                venue = ev.get("venue", {})
                country = venue.get("country", "")
                city = venue.get("city", "")

                # Only Singapore events
                if country.upper() not in ("SG", "SINGAPORE") and \
                   "singapore" not in city.lower():
                    continue

                eid = str(ev.get("id", ""))
                key = f"bit-{eid or artist + ev.get('datetime', '')}"
                if key in seen_ids:
                    continue
                seen_ids.add(key)

                dt_str = ev.get("datetime", "")
                try:
                    start_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    start_dt = start_dt.astimezone(SG_TZ)
                except Exception:
                    start_dt = now

                venue_name = venue.get("name", "")
                venue_location = f"{city}, {country}".strip(", ")

                offers = ev.get("offers", [])
                ticket_url = offers[0].get("url", "") if offers else ev.get("url", "")
                description_parts = [f"Artist: {artist}"]
                if venue_name:
                    description_parts.append(f"Venue: {venue_name}")
                if ticket_url:
                    description_parts.append(f"Tickets: {ticket_url}")

                events.append({
                    "id": key,
                    "title": f"{artist}",
                    "start_dt": start_dt,
                    "end_dt": None,
                    "description": "\n".join(description_parts),
                    "url": ticket_url,
                    "venue": venue_name,
                    "address": venue_location or "Singapore",
                    "type": "event",
                    "source": "bandsintown",
                })

    logger.info("Fetched %d artist concerts from Bandsintown", len(events))
    return events


def _encode(artist: str) -> str:
    from urllib.parse import quote
    return quote(artist, safe="")
