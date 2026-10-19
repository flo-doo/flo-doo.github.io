#!/usr/bin/env python3
"""Add or update one talk in data/events.json from GitHub workflow inputs."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "data" / "events.json"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def slugify(value: str) -> str:
    value = value.lower().replace("’", "").replace("'", "")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:120]


def display_date(value: str) -> str:
    parsed = dt.date.fromisoformat(value)
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def optional_float(value: str):
    return float(value) if value else None


def bool_env(name: str, default: bool = False) -> bool:
    raw = env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    date = env("TALK_DATE")
    event = env("TALK_EVENT")
    title = env("TALK_TITLE")
    if not date or not event or not title:
        raise SystemExit("TALK_DATE, TALK_EVENT, and TALK_TITLE are required.")
    dt.date.fromisoformat(date)

    doc = json.loads(EVENTS.read_text(encoding="utf-8"))
    location = env("TALK_LOCATION", "Virtual") or "Virtual"
    conference = env("TALK_CONFERENCE") or event
    record_id = env("TALK_ID") or slugify(f"{date}-{event}-{title}")

    participants = comma_list(env("TALK_PARTICIPANTS"))
    moderators = comma_list(env("TALK_MODERATORS"))
    alphabetical = bool_env("TALK_ALPHABETICAL", False)
    show_people = bool_env("TALK_SHOW_PEOPLE", False)
    parent_session = env("TALK_PARENT_SESSION")
    sponsor = env("TALK_SPONSOR")
    extra_note = env("TALK_NOTE")

    # Keep CV-level roster metadata in the record, but do not make the public
    # event card depend on a speaker list that may still change. Public roster
    # display is opt-in per event and defaults off in the workflow form.
    public_note_parts = []
    if parent_session:
        public_note_parts.append(f"Part of “{parent_session}”")
    if extra_note:
        public_note_parts.append(extra_note)
    if show_people and participants:
        label = "Panelists" if "panel" in (env("TALK_TYPE") or "").lower() else "Participants"
        if alphabetical:
            label += " (alphabetical)"
        public_note_parts.append(f"{label}: {', '.join(participants)}")
    if show_people and moderators:
        public_note_parts.append(f"Moderator{'s' if len(moderators) != 1 else ''}: {', '.join(moderators)}")

    item = {
        "id": record_id,
        "date": date,
        "displayDate": display_date(date),
        "event": event,
        "location": location,
        "type": env("TALK_TYPE") or "Invited talk",
        "title": title,
        "scope": env("TALK_SCOPE", "national") or "national",
        "conference": conference,
    }
    if env("TALK_TIME"):
        item["time"] = env("TALK_TIME")
    if public_note_parts:
        item["note"] = " · ".join(public_note_parts)
    if participants:
        item["participants"] = participants
    if moderators:
        item["moderators"] = moderators
    if alphabetical:
        item["participantOrder"] = "alphabetical"
    item["showPeople"] = show_people
    if parent_session:
        item["parentSession"] = parent_session
    if sponsor:
        item["sponsor"] = sponsor
    if env("TALK_URL"):
        item["url"] = env("TALK_URL")
    if env("TALK_CONFERENCE_URL"):
        item["conferenceUrl"] = env("TALK_CONFERENCE_URL")
    if location.lower() != "virtual":
        item["conferenceLocation"] = location

    lat = optional_float(env("TALK_LAT"))
    lng = optional_float(env("TALK_LNG"))
    if lat is None or lng is None:
        for known in doc.get("speakingLocations") or []:
            if str(known.get("label") or "").casefold() == location.casefold():
                lat = known.get("lat")
                lng = known.get("lng")
                break
    if lat is not None and lng is not None:
        item["lat"] = float(lat)
        item["lng"] = float(lng)

    events = doc.setdefault("events", [])
    existing_index = next((i for i, e in enumerate(events) if e.get("id") == record_id), None)
    if existing_index is None:
        # Older records may not have IDs; exact date + event + title is a safe fallback.
        existing_index = next(
            (
                i for i, e in enumerate(events)
                if e.get("date") == date
                and str(e.get("event") or "").casefold() == event.casefold()
                and str(e.get("title") or "").casefold() == title.casefold()
            ),
            None,
        )

    action = "updated" if existing_index is not None else "added"
    if existing_index is None:
        events.append(item)
    else:
        events[existing_index] = item

    events.sort(key=lambda e: e.get("date") or "")
    EVENTS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Talk {action}: {record_id}")
    if location.lower() != "virtual" and (lat is None or lng is None):
        print("Note: no map coordinates were available; the talk will still appear in the event list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
