#!/usr/bin/env python3
"""Reconcile publication-review issue decisions back into structured site data.

This runs before the daily ORCID refresh. It makes GitHub issue labels durable even
when an issue was closed manually, the `publication-review` label was removed, or
an older issue used a title-based key before a DOI became available.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBS = ROOT / "data" / "publications.json"
CURATED = ROOT / "data" / "publications-curated.json"
TOPICS = ROOT / "data" / "publication-topics.json"
SUPPRESSIONS = ROOT / "data" / "publication-suppressions.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "")

TOPIC_PREFIX = "pub:"
NO_TOPIC_LABEL = "pub:no-topic"
MARKER_RE = re.compile(r"<!--\s*publication-review-key:(.*?)\s*-->")
TITLE_RE = re.compile(r"^\*\*Title:\*\*\s*(.+?)\s*$", re.M)
DOI_RE = re.compile(r"^\*\*DOI:\*\*\s*`([^`]+)`\s*$", re.M)


def gh(*args: str, capture: bool = False) -> str:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=capture)
    return result.stdout if capture else ""


def load(path: Path, default):
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def norm_doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(
        r"^https?://(?:dx\.)?doi\.org/", "", str(value).strip(), flags=re.I
    ).lower().rstrip(".")


def key_for(pub: dict) -> str:
    doi = norm_doi(pub.get("doi"))
    return f"doi:{doi}" if doi else f"title:{norm_title(pub.get('title'))}"


def issue_marker(body: str) -> str | None:
    match = MARKER_RE.search(body or "")
    return match.group(1).strip() if match else None


def issue_title(body: str) -> str:
    match = TITLE_RE.search(body or "")
    return match.group(1).strip() if match else ""


def issue_doi(body: str) -> str:
    match = DOI_RE.search(body or "")
    return norm_doi(match.group(1)) if match else ""


def find_pub(items: list[dict], key: str, body: str = "") -> dict | None:
    exact = next((item for item in items if key_for(item) == key), None)
    if exact:
        return exact

    doi = key[4:] if key.startswith("doi:") else issue_doi(body)
    doi = norm_doi(doi)
    if doi:
        match = next((item for item in items if norm_doi(item.get("doi")) == doi), None)
        if match:
            return match

    title_key = key[6:] if key.startswith("title:") else ""
    if not title_key:
        title_key = norm_title(issue_title(body))
    if title_key:
        return next((item for item in items if norm_title(item.get("title")) == title_key), None)
    return None


def decision(issue: dict, valid_topics: set[str]) -> list[str] | None:
    names = {label.get("name", "") for label in issue.get("labels", [])}
    selected = sorted(
        name[len(TOPIC_PREFIX):]
        for name in names
        if name.startswith(TOPIC_PREFIX)
        and name != NO_TOPIC_LABEL
        and name[len(TOPIC_PREFIX):] in valid_topics
    )
    if selected:
        return selected
    if NO_TOPIC_LABEL in names:
        return []
    return None


def suppression_sets(config: dict):
    ids, dois, titles = set(), set(), set()
    for record in config.get("records", []):
        if record.get("id"):
            ids.add(str(record["id"]))
        if record.get("doi"):
            dois.add(norm_doi(record["doi"]))
        if record.get("title"):
            titles.add(norm_title(record["title"]))
    return ids, dois, titles


def is_suppressed(pub: dict, suppressions) -> bool:
    ids, dois, titles = suppressions
    return (
        (pub.get("id") and str(pub.get("id")) in ids)
        or (norm_doi(pub.get("doi")) and norm_doi(pub.get("doi")) in dois)
        or (norm_title(pub.get("title")) and norm_title(pub.get("title")) in titles)
    )


def main() -> None:
    if not REPO:
        raise SystemExit("GITHUB_REPOSITORY is required")

    pubs_doc = load(PUBS, {"updated": None, "count": 0, "publications": []})
    curated_doc = load(CURATED, {"updated": None, "count": 0, "publications": []})
    topic_config = load(
        TOPICS,
        {"labels": {}, "overrides": {}, "titleOverrides": {}, "reviewedUntagged": []},
    )
    suppression_config = load(SUPPRESSIONS, {"records": []})
    suppressions = suppression_sets(suppression_config)

    original_pubs = copy.deepcopy(pubs_doc.get("publications", []))
    original_curated = copy.deepcopy(curated_doc.get("publications", []))
    original_topics = copy.deepcopy(topic_config)

    pubs = [item for item in original_pubs if not is_suppressed(item, suppressions)]
    curated = [item for item in original_curated if not is_suppressed(item, suppressions)]

    issues = json.loads(
        gh(
            "issue", "list", "--repo", REPO, "--state", "all", "--limit", "300",
            "--json", "number,title,body,state,labels", capture=True,
        ) or "[]"
    )

    topic_config.setdefault("overrides", {})
    topic_config.setdefault("titleOverrides", {})
    reviewed_untagged = set(topic_config.get("reviewedUntagged", []))
    valid_topics = set(topic_config.get("labels", {}).keys())

    applied = 0
    promoted = 0
    for issue in issues:
        body = issue.get("body") or ""
        marker = issue_marker(body)
        if not marker:
            continue
        selected = decision(issue, valid_topics)
        if selected is None:
            continue

        pub = find_pub(pubs, marker, body) or find_pub(curated, marker, body)
        if pub is None:
            print(f"Review issue #{issue.get('number')} could not be matched to a publication; leaving it unchanged.")
            continue

        canonical_key = key_for(pub)
        doi = norm_doi(pub.get("doi"))
        title_key = norm_title(pub.get("title"))

        # Remove stale title-based decisions when a DOI has since become available.
        if marker.startswith("title:"):
            topic_config["titleOverrides"].pop(marker[6:], None)
            reviewed_untagged.discard(marker)

        if selected:
            if doi:
                topic_config["overrides"][doi] = selected
                topic_config["titleOverrides"].pop(title_key, None)
            else:
                topic_config["titleOverrides"][title_key] = selected
            reviewed_untagged.discard(canonical_key)
        else:
            if doi:
                topic_config["overrides"].pop(doi, None)
            topic_config["titleOverrides"].pop(title_key, None)
            reviewed_untagged.add(canonical_key)

        live_pub = find_pub(pubs, canonical_key, body)
        if live_pub is not None:
            live_pub["tags"] = selected

        curated_pub = find_pub(curated, canonical_key, body)
        if curated_pub is None:
            curated_pub = dict(pub)
            curated.append(curated_pub)
            promoted += 1
        curated_pub["tags"] = selected
        curated_pub["source"] = "Curated bibliography (human-reviewed)"
        applied += 1

    topic_config["reviewedUntagged"] = sorted(reviewed_untagged)

    pubs_changed = pubs != original_pubs
    curated_changed = curated != original_curated
    topics_changed = topic_config != original_topics
    today = dt.date.today().isoformat()

    if pubs_changed:
        pubs_doc["publications"] = pubs
        pubs_doc["count"] = len(pubs)
        pubs_doc["updated"] = today
        save(PUBS, pubs_doc)
    if curated_changed:
        curated_doc["publications"] = curated
        curated_doc["count"] = len(curated)
        curated_doc["updated"] = today
        save(CURATED, curated_doc)
    if topics_changed:
        save(TOPICS, topic_config)

    removed = (len(original_pubs) - len(pubs)) + (len(original_curated) - len(curated))
    print(
        f"Reconciled {applied} publication-review decision(s); "
        f"promoted {promoted} reviewed publication(s); removed {removed} suppressed record copy/copies."
    )


if __name__ == "__main__":
    main()
