#!/usr/bin/env python3
"""Refresh the site's publication index.

Why this script does not rely on Crossref's ORCID filter alone:
older papers can be present on an ORCID record even when the publisher did not
include the ORCID iD in Crossref metadata. The updater therefore uses the
public works shown by the ORCID web record as the primary bibliography,
enriches DOI-bearing works from Crossref, and merges in the existing cache.

The ORCID web endpoint used here is the same worksPage.json endpoint referenced
by ORCID's public web frontend. If that endpoint is temporarily unavailable,
the script falls back to Crossref + the existing cached data rather than
shrinking the live bibliography.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

ORCID = "0000-0001-6519-5222"
EMAIL = os.getenv("CROSSREF_MAILTO", "fdoo@som.umaryland.edu")
OUT = Path(__file__).resolve().parents[1] / "data" / "publications.json"
CROSSREF_API = "https://api.crossref.org/works"
ORCID_WEB = f"https://orcid.org/{ORCID}/worksPage.json"


def request_json(url: str, *, referer: str | None = None) -> dict[str, Any]:
    headers = {
        "User-Agent": f"FlorenceDooResearchSite/2.0 (mailto:{EMAIL})",
        "Accept": "application/json, text/plain, */*",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def unwrap(value: Any) -> str:
    """Return a useful scalar from ORCID's UI-style nested value objects."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("value", "content", "title", "name"):
            if key in value:
                found = unwrap(value[key])
                if found:
                    return found
    return ""


def first_date_crossref(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            vals = list(parts[0]) + [1, 1]
            y, m, d = vals[:3]
            try:
                return date(int(y), int(m), int(d)).isoformat()
            except (ValueError, TypeError):
                return str(y)
    return ""


def author_name(author: dict[str, Any]) -> str:
    family = (author.get("family") or "").strip()
    given = (author.get("given") or "").strip()
    if family and given:
        initials = "".join(part[0] for part in given.replace("-", " ").split() if part)
        return f"{family} {initials}".strip()
    return family or given or (author.get("name") or "").strip()


def normalize_crossref(item: dict[str, Any]) -> dict[str, Any]:
    titles = item.get("title") or []
    containers = item.get("container-title") or []
    published = first_date_crossref(item)
    year = int(published[:4]) if published[:4].isdigit() else None
    doi = (item.get("DOI") or "").lower().strip()
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


def external_id_value(ext: dict[str, Any], kind: str) -> str:
    type_value = unwrap(ext.get("externalIdentifierType") or ext.get("type")).lower()
    if type_value != kind.lower():
        return ""
    return unwrap(ext.get("externalIdentifierId") or ext.get("value")).strip()


def group_doi(group: dict[str, Any]) -> str:
    for ext in group.get("externalIdentifiers") or []:
        if not isinstance(ext, dict):
            continue
        doi = external_id_value(ext, "doi")
        if doi:
            return doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "")
    return ""


def find_first_work(group: dict[str, Any]) -> dict[str, Any]:
    for key in ("works", "workSummaries", "workSummary", "work"):
        value = group.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        if isinstance(value, dict):
            return value
    return group


def nested_title(work: dict[str, Any]) -> str:
    direct = unwrap(work.get("title"))
    if direct:
        return direct
    work_title = work.get("workTitle")
    if isinstance(work_title, dict):
        return unwrap(work_title.get("title") or work_title)
    return ""


def orcid_publication_date(work: dict[str, Any]) -> str:
    pd = work.get("publicationDate") or work.get("publication-date") or {}
    if not isinstance(pd, dict):
        return ""
    year = unwrap(pd.get("year"))
    month = unwrap(pd.get("month")) or "1"
    day = unwrap(pd.get("day")) or "1"
    if not year.isdigit():
        return ""
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        try:
            return date(int(year), 1, 1).isoformat()
        except ValueError:
            return year


def normalize_orcid_group(group: dict[str, Any]) -> dict[str, Any] | None:
    work = find_first_work(group)
    doi = group_doi(group)
    title = nested_title(work) or nested_title(group)
    journal = unwrap(work.get("journalTitle") or work.get("journal-title"))
    published = orcid_publication_date(work) or orcid_publication_date(group)
    year = int(published[:4]) if published[:4].isdigit() else None
    work_type = unwrap(work.get("workType") or work.get("type"))
    url = unwrap(work.get("url"))

    if not url:
        for ext in group.get("externalIdentifiers") or []:
            if isinstance(ext, dict):
                url = unwrap(ext.get("url") or ext.get("externalIdentifierUrl"))
                if url:
                    break
    if doi:
        url = f"https://doi.org/{doi}"

    if not title and not doi:
        return None

    return {
        "title": title or "Untitled",
        "year": year,
        "date": published,
        "journal": journal,
        "authors": [],
        "doi": doi,
        "type": work_type,
        "url": url,
    }


def fetch_orcid_groups() -> list[dict[str, Any]]:
    """Fetch all public ORCID work groups, defensively handling pagination."""
    all_groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0

    # ORCID's UI endpoint has historically paginated by offset. We stop when a
    # page adds no new groups, when the page is empty, or after a generous cap.
    for _ in range(30):
        params = urllib.parse.urlencode({"offset": offset, "sort": "date", "sortAsc": "false"})
        payload = request_json(f"{ORCID_WEB}?{params}", referer=f"https://orcid.org/{ORCID}")
        groups = payload.get("groups") or []
        if not isinstance(groups, list) or not groups:
            break

        new_count = 0
        for group in groups:
            if not isinstance(group, dict):
                continue
            gid = str(group.get("groupId") or "").strip()
            doi = group_doi(group)
            fallback = nested_title(find_first_work(group)).lower().strip()
            key = gid or doi or fallback or json.dumps(group, sort_keys=True)[:200]
            if key in seen:
                continue
            seen.add(key)
            all_groups.append(group)
            new_count += 1

        if new_count == 0:
            break
        offset += len(groups)
        if offset >= 1500:
            break

    return all_groups


def fetch_crossref_doi(doi: str) -> dict[str, Any] | None:
    if not doi:
        return None
    encoded = urllib.parse.quote(doi, safe="")
    try:
        payload = request_json(f"{CROSSREF_API}/{encoded}?mailto={urllib.parse.quote(EMAIL)}")
        message = payload.get("message")
        if isinstance(message, dict):
            return normalize_crossref(message)
    except Exception as exc:
        print(f"Crossref lookup failed for {doi}: {exc}", file=sys.stderr)
    return None


def fetch_crossref_orcid() -> list[dict[str, Any]]:
    params = {
        "filter": f"orcid:{ORCID}",
        "sort": "published",
        "order": "desc",
        "rows": "1000",
        "mailto": EMAIL,
    }
    data = request_json(CROSSREF_API + "?" + urllib.parse.urlencode(params))
    return [normalize_crossref(item) for item in data.get("message", {}).get("items", [])]


def load_existing() -> list[dict[str, Any]]:
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
        return payload.get("publications", []) if isinstance(payload, dict) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def merge_record(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    result = dict(old)
    for key, value in new.items():
        if value not in (None, "", [], {}):
            result[key] = value
    return result


def merge_publications(*collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    title_to_key: dict[str, str] = {}

    for collection in collections:
        for pub in collection:
            if not isinstance(pub, dict):
                continue
            doi = (pub.get("doi") or "").lower().strip()
            title_key = normalized_title(pub.get("title") or "")
            key = f"doi:{doi}" if doi else (f"title:{title_key}" if title_key else "")
            if not key:
                continue

            # If the same title was already cached without a DOI, merge it into
            # the DOI-bearing record instead of showing a duplicate.
            prior_title_key = title_to_key.get(title_key) if title_key else None
            if prior_title_key and prior_title_key != key:
                prior = by_key.pop(prior_title_key, {})
                by_key[key] = merge_record(prior, by_key.get(key, {}))

            by_key[key] = merge_record(by_key.get(key, {}), pub)
            if title_key:
                title_to_key[title_key] = key

    publications = list(by_key.values())
    publications.sort(
        key=lambda p: (p.get("date") or str(p.get("year") or ""), p.get("title") or ""),
        reverse=True,
    )
    return publications


def main() -> int:
    existing = load_existing()
    crossref_orcid: list[dict[str, Any]] = []
    try:
        crossref_orcid = fetch_crossref_orcid()
        print(f"Crossref ORCID filter returned {len(crossref_orcid)} works")
    except Exception as exc:
        print(f"Crossref ORCID query failed: {exc}", file=sys.stderr)

    orcid_records: list[dict[str, Any]] = []
    try:
        groups = fetch_orcid_groups()
        print(f"ORCID public record returned {len(groups)} work groups")
        for i, group in enumerate(groups, start=1):
            base = normalize_orcid_group(group)
            if not base:
                continue
            enriched = fetch_crossref_doi(base.get("doi") or "")
            orcid_records.append(merge_record(base, enriched or {}))
            if enriched and i % 15 == 0:
                time.sleep(0.15)
    except Exception as exc:
        print(f"ORCID public works query failed: {exc}", file=sys.stderr)

    publications = merge_publications(existing, crossref_orcid, orcid_records)
    if not publications:
        print("No publication records were available; preserving existing file.", file=sys.stderr)
        return 1

    sources = []
    if orcid_records:
        sources.append("ORCID public works")
    if crossref_orcid:
        sources.append("Crossref ORCID metadata")
    sources.append("existing curated cache")

    payload = {
        "updated_at": date.today().isoformat(),
        "source": ", enriched with DOI metadata; ".join(sources),
        "orcid": ORCID,
        "publications": publications,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(publications)} publications to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
