"""
Build an ICS calendar from movie and event dicts.
"""
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, Alarm, vText, vDatetime, vDate
import uuid

SG_TZ = ZoneInfo("Asia/Singapore")


def build_ics(
    movies: list[dict],
    events: list[dict],
    cal_name: str,
    reminder_minutes: int,
    refresh_interval: int,
) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Singapore Events Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", cal_name)
    cal.add("x-wr-timezone", "Asia/Singapore")
    cal.add("x-wr-caldesc", "Upcoming movies and events in Singapore")
    # Apple Calendar refresh interval in minutes
    cal.add("refresh-interval;value=duration", f"PT{refresh_interval}M")
    cal.add("x-published-ttl", f"PT{refresh_interval}M")

    for movie in movies:
        cal.add_component(_movie_to_event(movie, reminder_minutes))

    for ev in events:
        cal.add_component(_event_to_ical(ev, reminder_minutes))

    return cal.to_ical()


def _movie_to_event(movie: dict, reminder_minutes: int) -> Event:
    ev = Event()
    ev.add("uid", f"{movie['id']}@sg-events-calendar")
    ev.add("summary", f"[Movie] {movie['title']}")

    release: date = movie["release_date"]
    ev.add("dtstart", release)
    ev.add("dtend", release + timedelta(days=1))

    description_parts = []
    if movie.get("genres"):
        description_parts.append("Genres: " + ", ".join(movie["genres"]))
    if movie.get("overview"):
        description_parts.append(movie["overview"])
    if movie.get("tmdb_url"):
        description_parts.append(f"TMDB: {movie['tmdb_url']}")

    ev.add("description", "\n\n".join(description_parts))
    ev.add("url", movie.get("tmdb_url", ""))

    if movie.get("poster_url"):
        ev.add("attach", movie["poster_url"])

    ev.add("categories", ["Movies", "Singapore"])
    ev.add("dtstamp", datetime.now(timezone.utc))
    ev.add("transp", "TRANSPARENT")  # Don't block time (all-day)

    if reminder_minutes > 0:
        ev.add_component(_make_alarm(reminder_minutes))

    return ev


def _event_to_ical(event: dict, reminder_minutes: int) -> Event:
    ev = Event()
    ev.add("uid", f"{event['id']}@sg-events-calendar")
    ev.add("summary", f"[Event] {event['title']}")

    start_dt: datetime = event["start_dt"]
    if not start_dt.tzinfo:
        start_dt = start_dt.replace(tzinfo=SG_TZ)

    ev.add("dtstart", vDatetime(start_dt))

    end_dt = event.get("end_dt")
    if end_dt:
        if not end_dt.tzinfo:
            end_dt = end_dt.replace(tzinfo=SG_TZ)
        ev.add("dtend", vDatetime(end_dt))
    else:
        ev.add("dtend", vDatetime(start_dt + timedelta(hours=2)))

    description_parts = []
    if event.get("venue"):
        description_parts.append(f"Venue: {event['venue']}")
    if event.get("description"):
        description_parts.append(event["description"])
    if event.get("url"):
        description_parts.append(f"Tickets/Info: {event['url']}")

    ev.add("description", "\n\n".join(description_parts))

    if event.get("url"):
        ev.add("url", event["url"])

    if event.get("venue") or event.get("address"):
        ev.add("location", event.get("venue") or event.get("address", "Singapore"))

    ev.add("categories", ["Events", "Singapore"])
    ev.add("dtstamp", datetime.now(timezone.utc))

    if reminder_minutes > 0:
        ev.add_component(_make_alarm(reminder_minutes))

    return ev


def _make_alarm(minutes: int) -> Alarm:
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("trigger", timedelta(minutes=-minutes))
    alarm.add("description", "Event Reminder")
    return alarm
