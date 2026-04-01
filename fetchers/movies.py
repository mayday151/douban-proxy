"""
Fetch upcoming movie releases in Singapore from TMDB.
"""
import logging
from datetime import date, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

# TMDB genre IDs
GENRE_MAP = {
    "Action": 28,
    "Adventure": 12,
    "Animation": 16,
    "Comedy": 35,
    "Crime": 80,
    "Documentary": 99,
    "Drama": 18,
    "Fantasy": 14,
    "Horror": 27,
    "Music": 10402,
    "Mystery": 9648,
    "Romance": 10749,
    "Sci-Fi": 878,
    "Thriller": 53,
}

# Singapore's TMDB region code
SG_REGION = "SG"


def _genre_ids(genre_names: list[str]) -> list[int]:
    return [GENRE_MAP[g] for g in genre_names if g in GENRE_MAP]


def fetch_upcoming_movies(
    api_key: str,
    genres: list[str],
    must_watch_keywords: list[str],
    min_popularity: float,
    lookahead_days: int,
    language: str = "zh-CN",
) -> list[dict]:
    """
    Returns a list of movie event dicts combining:
    - Now playing in Singapore cinemas
    - Upcoming releases within lookahead_days
    """
    today = date.today()
    end_date = today + timedelta(days=lookahead_days)
    # Also look back 30 days to catch movies currently in theaters
    start_date = today - timedelta(days=30)
    wanted_genre_ids = set(_genre_ids(genres))

    movies = []
    seen_ids = set()

    def _collect(results: list[dict], en_map: dict[int, str] | None = None) -> None:
        for movie in results:
            mid = movie["id"]
            if mid in seen_ids:
                return
            seen_ids.add(mid)

            zh_title = movie.get("title", "")
            en_title = (en_map or {}).get(mid, "")
            # Build display title: 中文名 (English) or just whichever is available
            if zh_title and en_title and zh_title != en_title:
                display_title = f"{zh_title} ({en_title})"
            else:
                display_title = zh_title or en_title

            popularity = movie.get("popularity", 0)
            movie_genre_ids = set(movie.get("genre_ids", []))
            overview = movie.get("overview", "")

            # must_watch check against both titles
            combined_title = f"{zh_title} {en_title}".lower()
            is_must_watch = any(kw.lower() in combined_title for kw in must_watch_keywords)

            if not is_must_watch:
                if wanted_genre_ids and not (movie_genre_ids & wanted_genre_ids):
                    return
                if popularity < min_popularity:
                    return

            release_str = movie.get("release_date", "")
            if not release_str:
                return
            try:
                release_date = date.fromisoformat(release_str)
            except ValueError:
                return

            poster_path = movie.get("poster_path", "")
            movies.append(
                {
                    "id": f"movie-{mid}",
                    "title": display_title,
                    "release_date": release_date,
                    "overview": overview,
                    "popularity": popularity,
                    "poster_url": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else "",
                    "tmdb_url": f"https://www.themoviedb.org/movie/{mid}",
                    "genres": _genre_names(movie_genre_ids),
                    "type": "movie",
                }
            )

    with httpx.Client(timeout=15) as client:

        def _fetch_en_titles(ids: list[int]) -> dict[int, str]:
            """Fetch English titles for a batch of movie IDs."""
            en_map: dict[int, str] = {}
            # Re-fetch the same queries in en-US to get original titles
            return en_map  # filled lazily per-batch below

        def _get_results(url: str, params: dict) -> tuple[list, int]:
            """Fetch one page in both zh and en, return (zh_results, total_pages)."""
            zh_params = {**params, "language": language}
            en_params = {**params, "language": "en-US"}
            zh_resp = client.get(url, params=zh_params)
            zh_resp.raise_for_status()
            zh_data = zh_resp.json()
            zh_results = zh_data.get("results", [])

            # Build English title map for this page
            en_resp = client.get(url, params=en_params)
            en_resp.raise_for_status()
            en_data = en_resp.json()
            en_map = {m["id"]: m.get("title", "") for m in en_data.get("results", [])}

            return zh_results, zh_data.get("total_pages", 1), en_map

        # 1. Now playing in SG cinemas
        for page in range(1, 6):
            zh_results, total_pages, en_map = _get_results(
                f"{TMDB_BASE}/movie/now_playing",
                {"api_key": api_key, "region": SG_REGION, "page": page},
            )
            for movie in zh_results:
                _collect([movie], en_map)
            if page >= total_pages:
                break

        # 2. Upcoming releases
        page = 1
        while True:
            zh_results, total_pages, en_map = _get_results(
                f"{TMDB_BASE}/discover/movie",
                {
                    "api_key": api_key,
                    "region": SG_REGION,
                    "primary_release_date.gte": today.isoformat(),
                    "primary_release_date.lte": end_date.isoformat(),
                    "sort_by": "primary_release_date.asc",
                    "page": page,
                },
            )
            if not zh_results:
                break
            for movie in zh_results:
                _collect([movie], en_map)
            if page >= total_pages:
                break
            page += 1

    movies.sort(key=lambda m: m["release_date"])
    logger.info("Fetched %d movies for Singapore (now playing + upcoming)", len(movies))
    return movies


def _genre_names(genre_ids: set[int]) -> list[str]:
    reverse = {v: k for k, v in GENRE_MAP.items()}
    return [reverse[gid] for gid in genre_ids if gid in reverse]
