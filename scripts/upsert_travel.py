#!/usr/bin/env python3
"""Add or update one talk-related trip in data/travel-emissions.json."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "travel-emissions.json"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def slugify(value: str) -> str:
    value = value.lower().replace("’", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:120]


def optional_float(value: str):
    return float(value) if value else None


def bool_env(name: str, default: bool) -> bool:
    raw = env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def main() -> int:
    date = env("TRIP_DATE")
    label = env("TRIP_LABEL")
    destination = env("TRIP_DESTINATION").upper()
    if not date or not label or not destination:
        raise SystemExit("TRIP_DATE, TRIP_LABEL, and TRIP_DESTINATION are required.")
    dt.date.fromisoformat(date)

    doc = json.loads(LEDGER.read_text(encoding="utf-8"))
    record_id = env("TRIP_ID") or slugify(f"{date}-{label}")
    item = {
        "id": record_id,
        "label": label,
        "date": date,
        "status": env("TRIP_STATUS", "upcoming") or "upcoming",
        "origin": (env("TRIP_ORIGIN", "IAD") or "IAD").upper(),
        "destination": destination,
        "cabin": (env("TRIP_CABIN", "ECONOMY") or "ECONOMY").upper(),
        "roundTrip": bool_env("TRIP_ROUND_TRIP", True),
        "included": bool_env("TRIP_INCLUDED", True),
    }
    if env("TRIP_NOTE"):
        item["note"] = env("TRIP_NOTE")
    destination_lat = optional_float(env("TRIP_DESTINATION_LAT"))
    destination_lng = optional_float(env("TRIP_DESTINATION_LNG"))
    if destination_lat is not None and destination_lng is not None:
        item["destinationLat"] = destination_lat
        item["destinationLng"] = destination_lng

    trips = doc.setdefault("trips", [])
    existing_index = next((i for i, t in enumerate(trips) if t.get("id") == record_id), None)
    action = "updated" if existing_index is not None else "added"
    if existing_index is None:
        trips.append(item)
    else:
        trips[existing_index] = item
    trips.sort(key=lambda t: (t.get("date") or "0000-00-00", t.get("label") or ""))
    LEDGER.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Travel trip {action}: {record_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
