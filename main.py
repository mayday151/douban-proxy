"""
Singapore Events Calendar - Apple Calendar Subscription Server

Run:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8080

Then subscribe in Apple Calendar:
    File → New Calendar Subscription → http://localhost:8080/calendar.ics
"""
import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml
from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse

from calendar_builder import build_ics
from fetchers.movies import fetch_upcoming_movies
from fetchers.events import fetch_eventbrite_events, fetch_sistic_events

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.getenv("CALENDAR_CONFIG", "config.yaml"))

app = FastAPI(title="Singapore Events Calendar", docs_url=None, redoc_url=None)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@app.get("/")
def index():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Singapore Events Calendar</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; color: #1d1d1f; }
    h1 { font-size: 2rem; }
    .badge { background: #0071e3; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85rem; }
    code { background: #f5f5f7; padding: 2px 6px; border-radius: 4px; font-size: 0.9rem; }
    .step { margin: 16px 0; padding: 16px; background: #f5f5f7; border-radius: 10px; }
    a { color: #0071e3; }
  </style>
</head>
<body>
  <h1>🇸🇬 Singapore Events Calendar</h1>
  <p>A live calendar subscription for upcoming <strong>movies</strong> and <strong>events</strong> in Singapore.</p>

  <h2>Subscribe in Apple Calendar</h2>
  <div class="step">
    <strong>Step 1.</strong> Open Apple Calendar<br>
    <strong>Step 2.</strong> File → New Calendar Subscription<br>
    <strong>Step 3.</strong> Paste this URL:<br><br>
    <code>/calendar.ics</code> (full URL depends on where this is hosted)
  </div>

  <h2>Endpoints</h2>
  <ul>
    <li><a href="/calendar.ics">/calendar.ics</a> — Subscribe this URL in Apple Calendar</li>
    <li><a href="/health">/health</a> — Health check</li>
  </ul>

  <p>Edit <code>config.yaml</code> to customize genres, artists, and venues.</p>
</body>
</html>
""")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/calendar.ics")
def get_calendar():
    try:
        config = load_config()
    except Exception as e:
        raise HTTPException(500, f"Failed to load config: {e}")

    movies_cfg = config.get("movies", {})
    events_cfg = config.get("events", {})
    cal_cfg = config.get("calendar", {})

    all_movies = []
    if movies_cfg.get("enabled", True):
        tmdb_key = movies_cfg.get("tmdb_api_key", "")
        if tmdb_key and tmdb_key != "YOUR_TMDB_API_KEY":
            try:
                all_movies = fetch_upcoming_movies(
                    api_key=tmdb_key,
                    genres=movies_cfg.get("genres", []),
                    must_watch_keywords=movies_cfg.get("must_watch_keywords", []),
                    min_popularity=movies_cfg.get("min_popularity", 20),
                    lookahead_days=movies_cfg.get("lookahead_days", 90),
                )
            except Exception as e:
                logger.error("Movie fetch failed: %s", e)
        else:
            logger.warning("TMDB API key not set — skipping movies")

    all_events = []
    if events_cfg.get("enabled", True):
        keywords = events_cfg.get("keywords", [])
        tracked_venues = events_cfg.get("tracked_venues", [])
        lookahead = events_cfg.get("lookahead_days", 60)
        categories = events_cfg.get("categories", [])

        # Try Eventbrite
        eb_key = events_cfg.get("eventbrite_api_key", "")
        if eb_key and eb_key != "YOUR_EVENTBRITE_API_KEY":
            try:
                all_events += fetch_eventbrite_events(
                    api_key=eb_key,
                    categories=categories,
                    keywords=keywords,
                    tracked_venues=tracked_venues,
                    max_price_sgd=events_cfg.get("max_price_sgd", 0),
                    lookahead_days=lookahead,
                )
            except Exception as e:
                logger.error("Eventbrite fetch failed: %s", e)

        # Always try SISTIC (no key needed)
        try:
            sistic_events = fetch_sistic_events(
                keywords=keywords,
                tracked_venues=tracked_venues,
                lookahead_days=lookahead,
            )
            all_events += sistic_events
        except Exception as e:
            logger.error("SISTIC fetch failed: %s", e)

    ics_data = build_ics(
        movies=all_movies,
        events=all_events,
        cal_name=cal_cfg.get("name", "Singapore Events"),
        reminder_minutes=cal_cfg.get("reminder_minutes", 1440),
        refresh_interval=cal_cfg.get("refresh_interval", 60),
    )

    return Response(
        content=ics_data,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="singapore-events.ics"',
            "Cache-Control": f"max-age={cal_cfg.get('refresh_interval', 60) * 60}",
        },
    )
