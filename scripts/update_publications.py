#!/usr/bin/env python3
"""Refresh publication metadata for the website.

Primary zero-secret source: Crossref records containing Florence Doo's ORCID.
This is intentionally a cached build step rather than a browser-time API call.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ORCID = "0000-0001-6519-5222"
EMAIL = os.getenv("CROSSREF_MAILTO", "fdoo@som.umaryland.edu")
OUT = Path(__file__).resolve().parents[1] / "data" / "publications.json"
API = "https://api.crossref.org/works"


def request_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"FlorenceDooResearchSite/1.0 (mailto:{EMAIL})",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def first_date(item: dict) -> str:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            vals = list(parts[0]) + [1, 1]
            y, m, d = vals[:3]
            try:
                return date(int(y), int(m), int(d)).isoformat()
            except ValueError:
                return str(y)
    return ""


def author_name(a: dict) -> str:
    family = (a.get("family") or "").strip()
    given = (a.get("given") or "").strip()
    if family and given:
        initials = "".join(part[0] for part in given.replace("-", " ").split() if part)
        return f"{family} {initials}".strip()
    return family or given or (a.get("name") or "").strip()


def normalize(item: dict) -> dict:
    titles = item.get("title") or []
    containers = item.get("container-title") or []
    published = first_date(item)
    year = int(published[:4]) if published[:4].isdigit() else None
    doi = (item.get("DOI") or "").lower()
    return {
        "title": titles[0].strip() if titles else "Untitled",
        "year": year,
        "date": published,
        "journal": containers[0].strip() if containers else "",
        "authors": [name for a in item.get("author", []) if (name := author_name(a))],
        "doi": doi,
        "type": item.get("type") or "",
        "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
    }


def load_existing() -> list[dict]:
    try:
        return json.loads(OUT.read_text(encoding="utf-8")).get("publications", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def merge(primary: list[dict], existing: list[dict]) -> list[dict]:
    # Crossref ORCID coverage can be incomplete for older records, so retain seeded/manual works.
    by_key: dict[str, dict] = {}
    for p in existing + primary:
        key = (p.get("doi") or p.get("title") or "").lower().strip()
        if key:
            by_key[key] = p
    return sorted(by_key.values(), key=lambda p: (p.get("date") or str(p.get("year") or "")), reverse=True)


def main() -> int:
    params = {
        "filter": f"orcid:{ORCID}",
        "sort": "published",
        "order": "desc",
        "rows": "1000",
        "mailto": EMAIL,
    }
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        data = request_json(url)
        items = data.get("message", {}).get("items", [])
        refreshed = [normalize(i) for i in items]
        publications = merge(refreshed, load_existing())
        if not publications:
            raise RuntimeError("Crossref returned no publications and there is no existing seed data.")
        payload = {
            "updated_at": date.today().isoformat(),
            "source": "Crossref ORCID filter, merged with existing curated records",
            "orcid": ORCID,
            "publications": publications,
        }
        OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(publications)} publications to {OUT}")
        return 0
    except Exception as exc:
        print(f"Publication refresh failed: {exc}", file=sys.stderr)
        # Preserve existing site rather than erasing data on transient API failure.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
