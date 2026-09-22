#!/usr/bin/env python3
"""Refresh publication metadata while preserving the human-curated publication index.

Discovery policy (deliberately conservative):
  1. ORCID is the only automated discovery source for new publications.
  2. Crossref is used only to enrich an exact DOI already supplied by ORCID.
  3. Every run starts from the human-reviewed canonical publication file; only
     ORCID-discovered records may be carried forward from the mutable cache.

This avoids author-name web/API searches, which can attribute publications from
other authors with similar names. Newly discovered ORCID works remain untagged
until reviewed in data/publication-topic-review.json.

The script uses only the Python standard library.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ORCID = "0000-0001-6519-5222"
ROOT = Path(__file__).resolve().parents[1]
PUBS = ROOT / "data" / "publications.json"
CURATED = ROOT / "data" / "publications-curated.json"
TOPICS = ROOT / "data" / "publication-topics.json"
REVIEW = ROOT / "data" / "publication-topic-review.json"
UA = "florence-doo-site/1.1 (mailto:fdoo@som.umaryland.edu)"


def get_json(url: str, accept: str = "application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def norm_doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(
        r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I
    ).lower().rstrip(".")


CONTRIBUTION_NOTE_RE = re.compile(
    r"primary draft|supervision|project conceptualization|primary data gathering|"
    r"statistical interpretation|IRB primary investigator|ran analyses|co-wrote|edited primary draft",
    re.I,
)


def clean_citation(value):
    text = str(value or "").strip()
    while True:
        match = re.search(r"\s*\(([^()]*)\)\s*\.?\s*$", text)
        if not match or not CONTRIBUTION_NOTE_RE.search(match.group(1)):
            break
        text = text[: match.start()].rstrip()
        if text and not text.endswith("."):
            text += "."
    return text


def iso_from_parts(parts):
    try:
        values = list(parts or [])
        year = int(values[0])
        month = int(values[1]) if len(values) > 1 and values[1] else 1
        day = int(values[2]) if len(values) > 2 and values[2] else 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return None


def load_publication_file(path: Path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("publications", [])


def load_trusted_existing():
    """Return only records whose provenance is trusted.

    The human-reviewed canonical publication file is always authoritative. The mutable
    publication cache may contribute prior ORCID-discovered records, but never
    records discovered by the retired Crossref author-name search. This means a
    bad historical workflow run cannot permanently contaminate the site.
    """
    curated = load_publication_file(CURATED)
    current = load_publication_file(PUBS)

    # Keep only previous additions that were actually discovered from this ORCID.
    prior_orcid = []
    for item in current:
        source = str(item.get("source") or "").strip().lower()
        if source.startswith("orcid"):
            prior_orcid.append(item)

    return merge(curated, prior_orcid)


def load_topic_config():
    try:
        config = json.loads(TOPICS.read_text(encoding="utf-8"))
    except Exception:
        config = {}
    return {
        "labels": config.get("labels", {}),
        "overrides": {key.lower(): value for key, value in config.get("overrides", {}).items()},
        "titleOverrides": config.get("titleOverrides", {}),
        "reviewedUntagged": set(config.get("reviewedUntagged", [])),
    }


def topic_key(publication):
    doi = norm_doi(publication.get("doi"))
    return f"doi:{doi}" if doi else f"title:{norm_title(publication.get('title'))}"


def apply_tag_overrides(items):
    config = load_topic_config()
    for publication in items:
        doi = norm_doi(publication.get("doi"))
        existing_tags = list(publication.get("tags") or publication.get("topics") or [])
        explicit = config["overrides"].get(doi) if doi else None
        if explicit is None:
            explicit = config["titleOverrides"].get(norm_title(publication.get("title")))
        publication["tags"] = list(explicit) if explicit is not None else existing_tags
        publication.pop("topics", None)
    return items


def write_topic_review(items):
    config = load_topic_config()
    review = []
    for publication in items:
        if publication.get("tags") or publication.get("topics"):
            continue
        key = topic_key(publication)
        if key in config["reviewedUntagged"]:
            continue
        review.append(
            {
                "key": key,
                "year": publication.get("year"),
                "title": publication.get("title"),
                "doi": norm_doi(publication.get("doi")) or None,
            }
        )
    review.sort(
        key=lambda item: ((item.get("year") or 0), item.get("title") or ""),
        reverse=True,
    )
    REVIEW.write_text(
        json.dumps({"count": len(review), "items": review}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return review


def parse_orcid_group(group):
    summaries = group.get("work-summary") or group.get("workSummary") or []
    if not summaries:
        return None
    work = summaries[0]
    title = ((work.get("title") or {}).get("title") or {}).get("value") or ""
    pubdate = work.get("publication-date") or {}
    year = (pubdate.get("year") or {}).get("value")
    month = (pubdate.get("month") or {}).get("value")
    day = (pubdate.get("day") or {}).get("value")
    try:
        year = int(year) if year else None
    except Exception:
        year = None
    date = iso_from_parts([year, month, day]) if year else None

    doi = None
    pmid = None
    for external_id in (group.get("external-ids") or {}).get("external-id", []) or []:
        kind = (external_id.get("external-id-type") or "").lower()
        value = external_id.get("external-id-value")
        if kind == "doi" and value:
            doi = norm_doi(value)
        if kind in ("pmid", "pubmed") and value:
            pmid = str(value)

    url = (
        f"https://doi.org/{doi}"
        if doi
        else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None)
    )
    return {
        "title": title,
        "year": year,
        "date": date,
        "doi": doi or None,
        "pmid": pmid,
        "url": url,
        "citation": title,
        "source": "ORCID",
        "tags": [],
    }


def fetch_orcid():
    errors = []

    # Official ORCID public API first.
    try:
        data = get_json(
            f"https://pub.orcid.org/v3.0/{ORCID}/works",
            "application/vnd.orcid+json",
        )
        groups = data.get("group", [])
        output = [parse_orcid_group(group) for group in groups]
        return [item for item in output if item and item.get("title")], "ORCID API"
    except Exception as exc:
        errors.append(str(exc))

    # Public ORCID web-record JSON is a fallback, not an independent source.
    try:
        data = get_json(f"https://orcid.org/{ORCID}/worksPage.json")
        groups = data.get("groups") or data.get("group") or []
        output = []
        for group in groups:
            works = group.get("works") or group.get("work-summary") or []
            if not works:
                continue
            work = works[0]
            title = work.get("title") or work.get("workTitle") or ""
            if isinstance(title, dict):
                title = title.get("value") or title.get("title") or ""
            if isinstance(title, dict):
                title = title.get("value") or ""

            year = work.get("publicationDate") or work.get("publication-date") or work.get("year")
            if isinstance(year, dict):
                year = (
                    (year.get("year") or {}).get("value")
                    if isinstance(year.get("year"), dict)
                    else year.get("year")
                ) or year.get("value")
            try:
                year = int(str(year)[:4]) if year else None
            except Exception:
                year = None

            doi = None
            pmid = None
            external_ids = group.get("externalIdentifiers") or group.get("external-ids") or []
            if isinstance(external_ids, dict):
                external_ids = external_ids.get("external-id") or []
            for external_id in external_ids:
                kind = (external_id.get("type") or external_id.get("external-id-type") or "").lower()
                value = external_id.get("value") or external_id.get("external-id-value")
                if kind == "doi" and value:
                    doi = norm_doi(str(value))
                if kind in ("pmid", "pubmed") and value:
                    pmid = str(value)

            if title:
                output.append(
                    {
                        "title": title,
                        "year": year,
                        "date": f"{year:04d}-01-01" if year else None,
                        "doi": doi or None,
                        "pmid": pmid,
                        "url": (
                            f"https://doi.org/{doi}"
                            if doi
                            else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None)
                        ),
                        "citation": title,
                        "source": "ORCID",
                        "tags": [],
                    }
                )
        return output, "ORCID web record"
    except Exception as exc:
        errors.append(str(exc))

    print("ORCID unavailable:", " | ".join(errors), file=sys.stderr)
    return [], None


def parse_crossref_message(work):
    """Convert one exact-DOI Crossref record into enrichment metadata."""
    title = (work.get("title") or [""])[0]
    doi = norm_doi(work.get("DOI"))
    date_parts = (
        work.get("published-print")
        or work.get("published-online")
        or work.get("issued")
        or {}
    ).get("date-parts", [[None]])
    parts = date_parts[0] if date_parts and date_parts[0] else []
    year = parts[0] if parts else None
    exact_date = iso_from_parts(parts)
    journal = (work.get("container-title") or [""])[0]
    citation = (title + (f". {journal}." if journal else "")).strip()
    return {
        "title": title,
        "year": year,
        "date": exact_date,
        "doi": doi or None,
        "url": f"https://doi.org/{doi}" if doi else work.get("URL"),
        "citation": citation,
        "status": "published",
    }


def fetch_crossref_doi(doi: str):
    """Look up one DOI exactly. Never perform an author/name search."""
    doi = norm_doi(doi)
    if not doi:
        return None
    encoded = urllib.parse.quote(doi, safe="")
    try:
        data = get_json(f"https://api.crossref.org/works/{encoded}")
    except Exception as exc:
        # Some valid DOIs (e.g. DataCite records) are not in Crossref; this is benign.
        print(f"Crossref DOI enrichment skipped for {doi}: {exc}", file=sys.stderr)
        return None
    work = data.get("message") or {}
    returned = norm_doi(work.get("DOI"))
    if returned and returned != doi:
        print(
            f"Crossref returned mismatched DOI {returned} for requested {doi}; ignoring.",
            file=sys.stderr,
        )
        return None
    return parse_crossref_message(work)


def existing_lookup(existing):
    by_doi = {norm_doi(item.get("doi")): item for item in existing if norm_doi(item.get("doi"))}
    by_title = {norm_title(item.get("title")): item for item in existing if item.get("title")}
    return by_doi, by_title


def enrich_orcid_with_crossref(orcid_items, existing):
    """Use Crossref only for exact DOI enrichment of ORCID-discovered works.

    To keep the scheduled workflow fast and polite, lookups are limited to new or
    metadata-incomplete records. Existing well-populated curated records are not
    re-fetched every week.
    """
    by_doi, by_title = existing_lookup(existing)
    enriched = []
    exact_doi_lookups = 0

    for item in orcid_items:
        doi = norm_doi(item.get("doi"))
        title_key = norm_title(item.get("title"))
        old = (by_doi.get(doi) if doi else None) or by_title.get(title_key)
        needs_enrichment = (
            old is None
            or not old.get("date")
            or not old.get("url")
            or clean_citation(old.get("citation")) in ("", old.get("title") or "")
        )

        if doi and needs_enrichment:
            metadata = fetch_crossref_doi(doi)
            if metadata:
                exact_doi_lookups += 1
                # ORCID establishes identity/discovery; Crossref only fills blanks or
                # improves the machine-generated citation for a newly found work.
                for key in ("year", "date", "url", "status"):
                    if not item.get(key) and metadata.get(key):
                        item[key] = metadata[key]
                if not item.get("title") and metadata.get("title"):
                    item["title"] = metadata["title"]
                if item.get("citation") in (None, "", item.get("title")) and metadata.get("citation"):
                    item["citation"] = metadata["citation"]
                item["source"] = "ORCID + Crossref DOI"
        enriched.append(item)

    return enriched, exact_doi_lookups


def remove_unverified_legacy_crossref_discovery(existing, orcid_items, orcid_available):
    """Remove records created solely by the retired Crossref author-name search.

    Human-curated records are never touched. A legacy item whose source is exactly
    Crossref is retained only when the current ORCID record independently verifies
    the same DOI/title. Cleanup runs only when ORCID was successfully retrieved.
    """
    if not orcid_available:
        return existing, []

    orcid_dois = {norm_doi(item.get("doi")) for item in orcid_items if norm_doi(item.get("doi"))}
    orcid_titles = {norm_title(item.get("title")) for item in orcid_items if item.get("title")}
    kept = []
    removed = []

    for item in existing:
        source = str(item.get("source") or "").strip().lower()
        legacy_auto_only = source == "crossref" or source.startswith("crossref author")
        if not legacy_auto_only:
            kept.append(item)
            continue
        doi = norm_doi(item.get("doi"))
        title = norm_title(item.get("title"))
        verified = (doi and doi in orcid_dois) or (title and title in orcid_titles)
        if verified:
            kept.append(item)
        else:
            removed.append(item)

    return kept, removed


def merge(existing, discovered):
    by_doi, by_title = existing_lookup(existing)
    items = list(existing)

    for new_item in discovered:
        doi = norm_doi(new_item.get("doi"))
        title = norm_title(new_item.get("title"))
        old = (by_doi.get(doi) if doi else None) or by_title.get(title)
        if old:
            # Enrich without replacing curated citation or tags.
            for key in ("year", "date", "doi", "pmid", "url", "status"):
                if not old.get(key) and new_item.get(key):
                    old[key] = new_item[key]
            # Preserve the curated provenance label. ORCID is discovery/enrichment only.
            # The canonical curated record remains the source of truth.
        else:
            new_item.setdefault("tags", [])
            items.append(new_item)
            if doi:
                by_doi[doi] = new_item
            if title:
                by_title[title] = new_item

    # Final deduplication by DOI, otherwise normalized title.
    seen = set()
    result = []
    for item in items:
        key = norm_doi(item.get("doi")) or norm_title(item.get("title"))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main():
    # Rebuild from the trusted human-reviewed canonical publication file on every run. The current cache
    # is allowed to contribute only records previously discovered from this ORCID.
    # This intentionally discards historical broad Crossref/name-search results.
    existing = load_trusted_existing()
    orcid, orcid_source = fetch_orcid()

    enriched_orcid, doi_lookups = enrich_orcid_with_crossref(orcid, existing)
    merged = merge(existing, enriched_orcid)
    merged = apply_tag_overrides(merged)

    for publication in merged:
        publication["citation"] = clean_citation(publication.get("citation") or "")

    merged.sort(
        key=lambda publication: (
            publication.get("year") or 0,
            publication.get("date") or "",
            publication.get("title") or "",
        ),
        reverse=True,
    )

    output = {
        "updated": datetime.date.today().isoformat(),
        "count": len(merged),
        "publications": merged,
    }
    PUBS.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    review = write_topic_review(merged)

    print(
        f"Wrote {len(merged)} publications "
        f"({len(existing)} trusted curated/cache records, {len(orcid)} ORCID-discovered, "
        f"{doi_lookups} exact-DOI Crossref enrichment lookup(s))."
    )
    if not orcid_source:
        print(
            "ORCID was unavailable; no automated discovery or legacy cleanup was performed.",
            file=sys.stderr,
        )

    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py")], check=True)

    if review:
        print(
            f"Topic review needed for {len(review)} publication(s). "
            "See data/publication-topic-review.json."
        )


if __name__ == "__main__":
    main()
