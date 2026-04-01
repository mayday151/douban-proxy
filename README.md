# Singapore Events Calendar

A self-hosted Apple Calendar subscription that auto-populates upcoming **movies** (Singapore release dates) and **concerts / performances** in Singapore.

## How it works

1. You run a small Python web server
2. The server fetches events from TMDB (movies) and SISTIC / Eventbrite (performances)
3. It serves an `.ics` file at `/calendar.ics`
4. Apple Calendar subscribes to that URL and refreshes automatically

## Setup

### 1. Get API keys (free)

| Service | Where | Used for |
|---|---|---|
| [TMDB](https://www.themoviedb.org/settings/api) | Sign up → API → Developer | Movie release dates in SG |
| [Eventbrite](https://www.eventbrite.com/platform/api) | Optional | Concerts & ticketed events |

SISTIC events are scraped automatically — no key needed.

### 2. Configure preferences

Edit `config.yaml`:

```yaml
movies:
  tmdb_api_key: "paste_your_key_here"
  genres:           # what genres you care about
    - Action
    - Sci-Fi
    - Animation
  must_watch_keywords:  # always added regardless of genre/popularity
    - "Marvel"
    - "Star Wars"

events:
  keywords:
    - "concert"
    - "Singapore Symphony"
  tracked_venues:
    - "Esplanade"
    - "Gardens by the Bay"
```

### 3. Run the server

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

### 4. Subscribe in Apple Calendar

1. Open **Apple Calendar**
2. **File → New Calendar Subscription**
3. Enter: `http://localhost:8080/calendar.ics`
4. Set auto-refresh to **Every Hour**

> If you want to access from your iPhone or iPad too, deploy to a server (e.g. Railway, Fly.io, Render — all have free tiers) and use the public URL instead.

## Customization

All preferences live in `config.yaml`. Key settings:

| Setting | What it does |
|---|---|
| `movies.genres` | Only include movies matching these genres |
| `movies.must_watch_keywords` | Always include if title matches |
| `movies.min_popularity` | Filter out obscure films (TMDB score) |
| `events.keywords` | Keywords to search on Eventbrite |
| `events.tracked_venues` | Always track events at these venues |
| `calendar.reminder_minutes` | Alert N minutes before event (1440 = 24h) |
| `calendar.refresh_interval` | How often Apple Calendar pulls updates (minutes) |

## Deploying to the internet (optional)

So your iPhone and Mac both stay in sync without running a local server:

```bash
# Example: Railway (free tier)
railway up

# Or Fly.io
fly launch && fly deploy
```

Then subscribe using the public URL instead of localhost.
