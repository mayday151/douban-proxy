"""
Standalone script for GitHub Actions.
Reads config.yaml (with env var overrides), generates docs/singapore-events.ics.
"""
import logging
import os
from pathlib import Path

import yaml

from calendar_builder import build_ics
from fetchers.movies import fetch_upcoming_movies
from fetchers.events import fetch_eventbrite_events, fetch_sistic_events

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("docs/singapore-events.ics")


def load_config() -> dict:
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    # Allow env var overrides (useful in CI)
    if os.getenv("TMDB_API_KEY"):
        cfg.setdefault("movies", {})["tmdb_api_key"] = os.environ["TMDB_API_KEY"]
    if os.getenv("EVENTBRITE_API_KEY"):
        cfg.setdefault("events", {})["eventbrite_api_key"] = os.environ["EVENTBRITE_API_KEY"]

    return cfg


def main():
    cfg = load_config()
    movies_cfg = cfg.get("movies", {})
    events_cfg = cfg.get("events", {})
    cal_cfg = cfg.get("calendar", {})

    all_movies = []
    if movies_cfg.get("enabled", True):
        key = movies_cfg.get("tmdb_api_key", "")
        if key and key != "YOUR_TMDB_API_KEY":
            all_movies = fetch_upcoming_movies(
                api_key=key,
                genres=movies_cfg.get("genres", []),
                must_watch_keywords=movies_cfg.get("must_watch_keywords", []),
                min_popularity=movies_cfg.get("min_popularity", 20),
                lookahead_days=movies_cfg.get("lookahead_days", 90),
            )
        else:
            logger.warning("TMDB API key not set")

    all_events = []
    if events_cfg.get("enabled", True):
        keywords = events_cfg.get("keywords", [])
        tracked_venues = events_cfg.get("tracked_venues", [])
        lookahead = events_cfg.get("lookahead_days", 60)

        eb_key = events_cfg.get("eventbrite_api_key", "")
        if eb_key and eb_key != "YOUR_EVENTBRITE_API_KEY":
            all_events += fetch_eventbrite_events(
                api_key=eb_key,
                categories=events_cfg.get("categories", []),
                keywords=keywords,
                tracked_venues=tracked_venues,
                max_price_sgd=events_cfg.get("max_price_sgd", 0),
                lookahead_days=lookahead,
            )

        all_events += fetch_sistic_events(
            keywords=keywords,
            tracked_venues=tracked_venues,
            lookahead_days=lookahead,
        )

    ics_data = build_ics(
        movies=all_movies,
        events=all_events,
        cal_name=cal_cfg.get("name", "Singapore Events"),
        reminder_minutes=cal_cfg.get("reminder_minutes", 1440),
        refresh_interval=cal_cfg.get("refresh_interval", 60),
    )

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_bytes(ics_data)
    logger.info(
        "Written %d movies + %d events to %s",
        len(all_movies), len(all_events), OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
