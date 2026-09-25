#!/usr/bin/env python3
"""Refresh publication metadata while preserving the human-curated publication index.

Discovery policy (deliberately conservative):
  1. ORCID is the only automated discovery source for new works.
  2. Exact identifiers from ORCID (DOI/PMID) may be enriched through Crossref/PubMed.
  3. Human-curated records remain authoritative for citation wording and research tags.
  4. Newly discovered ORCID works are published only when they have enough verified
     metadata to render as a complete citation; incomplete records are quarantined
     in data/publication-metadata-review.json instead of creating gaps on the site.

No author-name search is used, so similarly named authors cannot be imported by a
broad search. The script uses only the Python standard library.
"""
from __future__ import annotations

import copy
import datetime
import html
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
METADATA_REVIEW = ROOT / "data" / "publication-metadata-review.json"
UA = "florence-doo-site/1.2 (mailto:fdoo@som.umaryland.edu)"


def get_json(url: str, accept: str = "application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def plain_text(value) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", plain_text(value).lower())


def norm_doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(
        r"^https?://(?:dx\.)?doi\.org/", "", str(value).strip(), flags=re.I
    ).lower().rstrip(".")


def norm_pmid(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


CONTRIBUTION_NOTE_RE = re.compile(
    r"primary draft|supervision|project conceptualization|primary data gathering|"
    r"statistical interpretation|IRB primary investigator|ran analyses|co-wrote|edited primary draft",
    re.I,
)


def clean_citation(value):
    text = plain_text(value)
    while True:
        match = re.search(r"\s*\(([^()]*)\)\s*\.?\s*$", text)
        if not match or not CONTRIBUTION_NOTE_RE.search(match.group(1)):
            break
        text = text[: match.start()].rstrip()
        if text and not text.endswith("."):
            text += "."
    return text


def is_in_press(publication):
    status = str(publication.get("status") or "").strip().lower()
    citation = clean_citation(publication.get("citation") or "")
    return status in {"accepted", "in press", "in-press"} or bool(
        re.search(r"\bAccepted\b|\bin press\b", citation, re.I)
    )


def citation_has_authors(publication) -> bool:
    """Require an author/contributor segment before the title for auto-added works."""
    citation = norm_title(publication.get("citation") or "")
    title = norm_title(publication.get("title") or "")
    if not citation or not title:
        return False
    position = citation.find(title)
    return position > 0


def human_date(iso_date):
    try:
        parsed = datetime.date.fromisoformat(str(iso_date))
    except Exception:
        return None
    return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"


def promote_citation_to_published(citation, metadata):
    """Replace a stale accepted/in-press suffix after exact-ID publication verification."""
    text = clean_citation(citation)
    text = re.sub(
        r"\s*(?:[,.]?\s*Accepted\b.*|[,.]?\s*\(?in[ -]?press\)?\.?)\s*$",
        "",
        text,
        flags=re.I,
    ).rstrip(" .,;")
    if text:
        text += "."
    published = human_date(metadata.get("date"))
    if published:
        text += f" Published online {published}."
    return text.strip()


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
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("publications", [])
    except Exception:
        return []


def prior_orcid_records():
    current = load_publication_file(PUBS)
    return [
        item
        for item in current
        if str(item.get("source") or "").strip().lower().startswith("orcid")
    ]


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


def external_id_entries(*containers):
    """Yield external identifier dictionaries from API and web-record shapes."""
    stack = [node for node in containers if node]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        kind = node.get("external-id-type") or node.get("type") or node.get("externalIdentifierType")
        value = node.get("external-id-value") or node.get("value") or node.get("externalIdentifierId")
        if kind and value:
            yield node
        for key, child in node.items():
            if key in {
                "external-id",
                "external-ids",
                "externalIdentifiers",
                "external-identifier",
                "externalIdentifier",
            }:
                stack.append(child)


def identifiers_from_orcid(group, works):
    values = {"doi": None, "pmid": None, "isbn": None, "eid": None, "external_url": None}
    nodes = [
        group.get("external-ids"),
        group.get("externalIdentifiers"),
        group.get("externalIdentifier"),
    ]
    for work in works:
        if isinstance(work, dict):
            nodes.extend(
                [
                    work.get("external-ids"),
                    work.get("externalIdentifiers"),
                    work.get("externalIdentifier"),
                ]
            )
    for entry in external_id_entries(*nodes):
        kind = str(
            entry.get("external-id-type")
            or entry.get("type")
            or entry.get("externalIdentifierType")
            or ""
        ).lower()
        value = str(
            entry.get("external-id-value")
            or entry.get("value")
            or entry.get("externalIdentifierId")
            or ""
        ).strip()
        url_obj = entry.get("external-id-url") or entry.get("url")
        url_value = url_obj.get("value") if isinstance(url_obj, dict) else url_obj
        if kind == "doi" and value:
            values["doi"] = norm_doi(value)
        elif kind in {"pmid", "pubmed"} and value:
            values["pmid"] = norm_pmid(value)
        elif kind == "isbn" and value:
            values["isbn"] = value
        elif kind in {"eid", "scopus"} and value:
            values["eid"] = value
        if url_value and str(url_value).startswith(("http://", "https://")):
            values["external_url"] = str(url_value)
    return values


def value_from_orcid(value):
    if isinstance(value, dict):
        if "value" in value:
            return value.get("value")
        if "title" in value:
            return value_from_orcid(value.get("title"))
    return value


def parse_orcid_group(group):
    summaries = group.get("work-summary") or group.get("workSummary") or group.get("works") or []
    if not summaries:
        return None
    works = [work for work in summaries if isinstance(work, dict)]
    if not works:
        return None

    # Aggregate IDs across the ORCID group. One source can carry the DOI even when
    # the display/preferred source does not.
    ids = identifiers_from_orcid(group, works)

    work = works[0]
    title_obj = work.get("title") or work.get("workTitle") or ""
    title = plain_text(value_from_orcid(title_obj) or "")
    if not title:
        for candidate in works[1:]:
            title = plain_text(value_from_orcid(candidate.get("title") or candidate.get("workTitle")) or "")
            if title:
                work = candidate
                break

    pubdate = work.get("publication-date") or work.get("publicationDate") or {}
    if isinstance(pubdate, dict):
        year = value_from_orcid(pubdate.get("year"))
        month = value_from_orcid(pubdate.get("month"))
        day = value_from_orcid(pubdate.get("day"))
    else:
        year, month, day = pubdate, None, None
    if not year:
        year = value_from_orcid(work.get("year"))
    try:
        year = int(str(year)[:4]) if year else None
    except Exception:
        year = None
    date = iso_from_parts([year, month, day]) if year else None

    work_url = value_from_orcid(work.get("url"))
    if not (isinstance(work_url, str) and work_url.startswith(("http://", "https://"))):
        work_url = None
    doi = ids["doi"]
    pmid = ids["pmid"]
    url = (
        f"https://doi.org/{doi}"
        if doi
        else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (work_url or ids["external_url"]))
    )
    work_type = work.get("type") or work.get("workType")
    if isinstance(work_type, dict):
        work_type = value_from_orcid(work_type)

    return {
        "title": title,
        "year": year,
        "date": date,
        "doi": doi or None,
        "pmid": pmid or None,
        "url": url,
        "citation": title,
        "work_type": str(work_type or "").lower() or None,
        "source": "ORCID",
        "tags": [],
    }


def parse_orcid_web_group(group):
    works = group.get("works") or group.get("work-summary") or group.get("workSummary") or []
    if not works:
        return None
    # Normalize enough of the web shape for the common parser.
    normalized = dict(group)
    normalized["works"] = works
    return parse_orcid_group(normalized)


def fetch_orcid():
    errors = []
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

    try:
        data = get_json(f"https://orcid.org/{ORCID}/worksPage.json")
        groups = data.get("groups") or data.get("group") or []
        output = [parse_orcid_web_group(group) for group in groups]
        return [item for item in output if item and item.get("title")], "ORCID web record"
    except Exception as exc:
        errors.append(str(exc))

    print("ORCID unavailable:", " | ".join(errors), file=sys.stderr)
    return [], None


def name_initials(given: str) -> str:
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", plain_text(given))
    return "".join(token[0].upper() for token in tokens if token)


def crossref_authors(work) -> str:
    names = []
    for author in work.get("author") or []:
        family = plain_text(author.get("family") or "")
        given = plain_text(author.get("given") or "")
        literal = plain_text(author.get("name") or "")
        if family:
            initials = name_initials(given)
            names.append(f"{family} {initials}".strip())
        elif literal:
            names.append(literal)
    return ", ".join(names)


def month_abbrev(month: int) -> str:
    try:
        return datetime.date(2000, int(month), 1).strftime("%b")
    except Exception:
        return ""


def citation_date(parts) -> str:
    values = list(parts or [])
    if not values:
        return ""
    try:
        year = int(values[0])
    except Exception:
        return ""
    if len(values) > 2 and values[1] and values[2]:
        return f"{year} {month_abbrev(int(values[1]))} {int(values[2])}"
    if len(values) > 1 and values[1]:
        return f"{year} {month_abbrev(int(values[1]))}"
    return str(year)


def first_date_parts(work, *keys):
    for key in keys:
        date_parts = (work.get(key) or {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            return list(date_parts[0])
    return []


def crossref_citation(work, title: str, doi: str, best_parts) -> str:
    authors = crossref_authors(work)
    container = plain_text((work.get("container-title") or [""])[0])
    publisher = plain_text(work.get("publisher") or "")
    volume = plain_text(work.get("volume") or "")
    issue = plain_text(work.get("issue") or "")
    pages = plain_text(work.get("page") or work.get("article-number") or "")
    work_type = str(work.get("type") or "").lower()

    # Use issue/print date for a mature journal citation when available; retain
    # first-online as the record's machine date for sorting/latest-publication logic.
    if work_type == "book-chapter":
        display_parts = best_parts
    else:
        display_parts = (
            first_date_parts(work, "published-print", "issued", "published-online")
            if (volume or issue or pages)
            else best_parts
        )
    date_text = citation_date(display_parts)

    pieces = []
    if authors:
        pieces.append(authors.rstrip(".") + ".")
    pieces.append(title.rstrip(".") + ".")

    if work_type == "book-chapter":
        if container:
            pieces.append(f"In: {container.rstrip('.') }.")
        if publisher:
            pieces.append(publisher.rstrip(".") + ".")
        if date_text:
            pieces.append(date_text + ".")
        if pages:
            pieces.append(f"pp. {pages}.")
    else:
        if container:
            pieces.append(container.rstrip(".") + ".")
        bibliographic = date_text
        if volume:
            bibliographic += (";" if bibliographic else "") + volume
            if issue:
                bibliographic += f"({issue})"
            if pages:
                bibliographic += f":{pages}"
        elif pages:
            bibliographic += (":" if bibliographic else "") + pages
        if bibliographic:
            pieces.append(bibliographic.rstrip(".") + ".")

    if doi:
        pieces.append(f"doi: {doi}.")
    return " ".join(piece for piece in pieces if piece).strip()


def parse_crossref_message(work):
    title = plain_text((work.get("title") or [""])[0])
    doi = norm_doi(work.get("DOI"))
    best_parts = first_date_parts(work, "published-online", "published-print", "issued")
    exact_date = iso_from_parts(best_parts)
    year = best_parts[0] if best_parts else None
    try:
        year = int(year) if year else None
    except Exception:
        year = None
    return {
        "title": title,
        "year": year,
        "date": exact_date,
        "doi": doi or None,
        "url": f"https://doi.org/{doi}" if doi else work.get("URL"),
        "citation": crossref_citation(work, title, doi, best_parts),
        "status": "published",
        "work_type": str(work.get("type") or "").lower() or None,
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
        print(f"Crossref DOI enrichment skipped for {doi}: {exc}", file=sys.stderr)
        return None
    work = data.get("message") or {}
    returned = norm_doi(work.get("DOI"))
    if returned and returned != doi:
        print(f"Crossref returned mismatched DOI {returned} for requested {doi}; ignoring.", file=sys.stderr)
        return None
    return parse_crossref_message(work)


def parse_pubmed_summary(record, pmid: str):
    title = plain_text(record.get("title") or "")
    authors = ", ".join(plain_text(a.get("name") or "") for a in record.get("authors") or [] if a.get("name"))
    journal = plain_text(record.get("source") or "")
    pubdate = plain_text(record.get("pubdate") or "")
    volume = plain_text(record.get("volume") or "")
    issue = plain_text(record.get("issue") or "")
    pages = plain_text(record.get("pages") or "")
    doi = ""
    for article_id in record.get("articleids") or []:
        if str(article_id.get("idtype") or "").lower() == "doi":
            doi = norm_doi(article_id.get("value"))
            break
    year_match = re.search(r"\b(19|20)\d{2}\b", pubdate)
    year = int(year_match.group(0)) if year_match else None
    citation_parts = []
    if authors:
        citation_parts.append(authors.rstrip(".") + ".")
    if title:
        citation_parts.append(title.rstrip(".") + ".")
    if journal:
        citation_parts.append(journal.rstrip(".") + ".")
    biblio = pubdate
    if volume:
        biblio += (";" if biblio else "") + volume
        if issue:
            biblio += f"({issue})"
        if pages:
            biblio += f":{pages}"
    if biblio:
        citation_parts.append(biblio.rstrip(".") + ".")
    if doi:
        citation_parts.append(f"doi: {doi}.")
    citation_parts.append(f"PMID: {pmid}.")
    return {
        "title": title,
        "year": year,
        "doi": doi or None,
        "pmid": pmid,
        "url": f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "citation": " ".join(citation_parts),
        "status": "published",
    }


def fetch_pubmed_pmid(pmid: str):
    pmid = norm_pmid(pmid)
    if not pmid:
        return None
    try:
        data = get_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urllib.parse.urlencode({"db": "pubmed", "id": pmid, "retmode": "json"})
        )
    except Exception as exc:
        print(f"PubMed enrichment skipped for PMID {pmid}: {exc}", file=sys.stderr)
        return None
    record = (data.get("result") or {}).get(pmid) or {}
    return parse_pubmed_summary(record, pmid) if record else None


def existing_lookup(existing):
    by_doi = {norm_doi(item.get("doi")): item for item in existing if norm_doi(item.get("doi"))}
    by_pmid = {norm_pmid(item.get("pmid")): item for item in existing if norm_pmid(item.get("pmid"))}
    by_title = {norm_title(item.get("title")): item for item in existing if item.get("title")}
    return by_doi, by_pmid, by_title


def find_existing(item, existing):
    by_doi, by_pmid, by_title = existing_lookup(existing)
    doi = norm_doi(item.get("doi"))
    pmid = norm_pmid(item.get("pmid"))
    title = norm_title(item.get("title"))
    return (by_doi.get(doi) if doi else None) or (by_pmid.get(pmid) if pmid else None) or by_title.get(title)


def needs_metadata_enrichment(item) -> bool:
    citation = clean_citation(item.get("citation") or "")
    return (
        not item.get("year")
        or not item.get("url")
        or not citation
        or not citation_has_authors(item)
        or is_in_press(item)
    )


def enrich_orcid(orcid_items, cache):
    """Enrich ORCID works only through identifiers that ORCID itself supplied."""
    cache_lookup = existing_lookup(cache)
    enriched = []
    crossref_lookups = 0
    pubmed_lookups = 0

    for raw in orcid_items:
        item = copy.deepcopy(raw)
        doi = norm_doi(item.get("doi"))
        pmid = norm_pmid(item.get("pmid"))
        title_key = norm_title(item.get("title"))
        by_doi, by_pmid, by_title = cache_lookup
        old = (by_doi.get(doi) if doi else None) or (by_pmid.get(pmid) if pmid else None) or by_title.get(title_key)

        # Reuse a previously verified auto record as a cache, while allowing fresh
        # ORCID IDs/dates to fill any newly available fields.
        if old and str(old.get("source") or "").lower().startswith("orcid") and not needs_metadata_enrichment(old):
            cached = copy.deepcopy(old)
            for key in ("doi", "pmid", "year", "date", "url", "work_type"):
                if item.get(key):
                    cached[key] = item[key]
            item = cached
            doi = norm_doi(item.get("doi"))
            pmid = norm_pmid(item.get("pmid"))

        # PMID is useful for discovering the DOI and a complete medical citation.
        pubmed = None
        if pmid and needs_metadata_enrichment(item):
            pubmed = fetch_pubmed_pmid(pmid)
            if pubmed:
                pubmed_lookups += 1
                for key in ("year", "pmid", "doi", "url", "status"):
                    if pubmed.get(key):
                        item[key] = pubmed[key]
                if pubmed.get("title"):
                    item["title"] = pubmed["title"]
                if pubmed.get("citation"):
                    item["citation"] = pubmed["citation"]
                item["source"] = "ORCID + PubMed PMID"
                doi = norm_doi(item.get("doi"))

        # DOI metadata is the preferred canonical title/link source for new works.
        if doi and needs_metadata_enrichment(item):
            crossref = fetch_crossref_doi(doi)
            if crossref:
                crossref_lookups += 1
                for key in ("year", "date", "doi", "url", "status", "work_type"):
                    if crossref.get(key):
                        item[key] = crossref[key]
                # For machine-added ORCID works, an exact DOI can correct a generic
                # host title (e.g. a book title) to the actual chapter/article title.
                if crossref.get("title"):
                    item["title"] = crossref["title"]
                if crossref.get("citation"):
                    item["citation"] = crossref["citation"]
                item["source"] = "ORCID + Crossref DOI"

        enriched.append(item)

    return enriched, crossref_lookups, pubmed_lookups


def auto_publication_reason(item):
    """Return None when a newly discovered work is safe to publish, else a reason."""
    if not item.get("title"):
        return "missing title"
    if not item.get("year"):
        return "missing publication year"
    if not (norm_doi(item.get("doi")) or norm_pmid(item.get("pmid")) or item.get("url")):
        return "no stable publication URL/identifier"
    if not citation_has_authors(item):
        return "citation is incomplete (no author/contributor segment before title)"
    return None


def write_metadata_review(items):
    METADATA_REVIEW.write_text(
        json.dumps({"count": len(items), "items": items}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def merge(existing, discovered):
    by_doi, by_pmid, by_title = existing_lookup(existing)
    items = list(existing)

    for new_item in discovered:
        doi = norm_doi(new_item.get("doi"))
        pmid = norm_pmid(new_item.get("pmid"))
        title = norm_title(new_item.get("title"))
        old = (by_doi.get(doi) if doi else None) or (by_pmid.get(pmid) if pmid else None) or by_title.get(title)
        if old:
            verified_published = (
                bool(doi or pmid)
                and str(new_item.get("status") or "").lower() == "published"
            )
            was_in_press = is_in_press(old)
            for key in ("year", "date", "doi", "pmid", "url", "status", "work_type"):
                if verified_published and key in {"year", "date", "doi", "pmid", "url", "status"}:
                    if new_item.get(key):
                        old[key] = new_item[key]
                elif not old.get(key) and new_item.get(key):
                    old[key] = new_item[key]
            if verified_published and was_in_press:
                old["citation"] = promote_citation_to_published(old.get("citation") or "", new_item)
        else:
            new_item.setdefault("tags", [])
            items.append(new_item)
            if doi:
                by_doi[doi] = new_item
            if pmid:
                by_pmid[pmid] = new_item
            if title:
                by_title[title] = new_item

    # Deduplicate across any shared DOI, PMID, or normalized title.
    seen_doi, seen_pmid, seen_title = set(), set(), set()
    result = []
    for item in items:
        doi = norm_doi(item.get("doi"))
        pmid = norm_pmid(item.get("pmid"))
        title = norm_title(item.get("title"))
        if (doi and doi in seen_doi) or (pmid and pmid in seen_pmid) or (title and title in seen_title):
            continue
        if doi:
            seen_doi.add(doi)
        if pmid:
            seen_pmid.add(pmid)
        if title:
            seen_title.add(title)
        result.append(item)
    return result


def main():
    curated = load_publication_file(CURATED)
    prior_auto = prior_orcid_records()
    cache = curated + prior_auto
    orcid, orcid_source = fetch_orcid()

    metadata_review = []
    if orcid_source:
        enriched_orcid, doi_lookups, pubmed_lookups = enrich_orcid(orcid, cache)
        curated_lookup = existing_lookup(curated)
        accepted_discovery = []
        for item in enriched_orcid:
            by_doi, by_pmid, by_title = curated_lookup
            doi = norm_doi(item.get("doi"))
            pmid = norm_pmid(item.get("pmid"))
            title = norm_title(item.get("title"))
            matches_curated = (
                (doi and doi in by_doi)
                or (pmid and pmid in by_pmid)
                or (title and title in by_title)
            )
            reason = auto_publication_reason(item)
            if matches_curated or reason is None:
                accepted_discovery.append(item)
            else:
                metadata_review.append(
                    {
                        "title": item.get("title"),
                        "year": item.get("year"),
                        "doi": norm_doi(item.get("doi")) or None,
                        "pmid": norm_pmid(item.get("pmid")) or None,
                        "reason": reason,
                    }
                )
        # Important: after a successful ORCID fetch, rebuild all machine-added
        # records from fresh ORCID data instead of carrying malformed historical
        # cache entries forward forever.
        merged = merge(copy.deepcopy(curated), accepted_discovery)
    else:
        doi_lookups = 0
        pubmed_lookups = 0
        # If ORCID is temporarily unavailable, retain only previously auto-added
        # records that already meet the publication-quality gate.
        safe_prior = []
        for item in prior_auto:
            reason = auto_publication_reason(item)
            if reason is None:
                safe_prior.append(item)
            else:
                metadata_review.append(
                    {
                        "title": item.get("title"),
                        "year": item.get("year"),
                        "doi": norm_doi(item.get("doi")) or None,
                        "pmid": norm_pmid(item.get("pmid")) or None,
                        "reason": reason,
                    }
                )
        merged = merge(copy.deepcopy(curated), safe_prior)

    merged = apply_tag_overrides(merged)
    for publication in merged:
        publication["title"] = plain_text(publication.get("title") or "")
        publication["citation"] = clean_citation(publication.get("citation") or "")

    merged.sort(
        key=lambda publication: (
            publication.get("year") or 0,
            publication.get("date") or "",
            publication.get("title") or "",
        ),
        reverse=True,
    )
    metadata_review.sort(key=lambda item: ((item.get("year") or 0), item.get("title") or ""), reverse=True)
    write_metadata_review(metadata_review)

    try:
        previous_output = json.loads(PUBS.read_text(encoding="utf-8")) if PUBS.exists() else {}
    except Exception:
        previous_output = {}
    publications_changed = previous_output.get("publications") != merged
    updated = (
        datetime.date.today().isoformat()
        if publications_changed
        else previous_output.get("updated") or datetime.date.today().isoformat()
    )
    output = {"updated": updated, "count": len(merged), "publications": merged}
    PUBS.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    review = write_topic_review(merged)

    print(
        f"Wrote {len(merged)} publications from {len(curated)} curated + verified ORCID records "
        f"({len(orcid)} ORCID works; {doi_lookups} Crossref DOI lookup(s); "
        f"{pubmed_lookups} PubMed PMID lookup(s); {len(metadata_review)} held for metadata review)."
    )
    if not orcid_source:
        print("ORCID was unavailable; safe prior auto-added records were retained.", file=sys.stderr)

    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py")], check=True)

    if review:
        print(f"Topic review needed for {len(review)} publication(s). See data/publication-topic-review.json.")
    if metadata_review:
        print(
            f"Metadata review needed for {len(metadata_review)} ORCID publication(s); "
            "they were not published to the site. See data/publication-metadata-review.json."
        )


if __name__ == "__main__":
    main()
