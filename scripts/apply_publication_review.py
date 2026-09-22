#!/usr/bin/env python3
"""Apply research-area labels selected on a GitHub publication-review issue.

A reviewer only needs to use the issue's Labels control. Topic labels are mapped
back to data/publication-topics.json and to the human-curated publication list.
The issue may carry multiple topic labels. Close the issue manually when the
selection is complete.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT_PATH = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
PUBS = ROOT / "data" / "publications.json"
CURATED = ROOT / "data" / "publications-curated.json"
TOPICS = ROOT / "data" / "publication-topics.json"
REVIEW = ROOT / "data" / "publication-topic-review.json"
BUILD = ROOT / "scripts" / "build_site.py"

REVIEW_LABEL = "publication-review"
TOPIC_PREFIX = "pub:"
NO_TOPIC_LABEL = "pub:no-topic"
MARKER_RE = re.compile(r"<!--\s*publication-review-key:(.*?)\s*-->")


def norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def norm_doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I).lower().rstrip(".")


def key_for(pub: dict) -> str:
    doi = norm_doi(pub.get("doi"))
    return f"doi:{doi}" if doi else f"title:{norm_title(pub.get('title'))}"


def load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_pub(items: list[dict], key: str) -> dict | None:
    return next((item for item in items if key_for(item) == key), None)


def main() -> int:
    if not EVENT_PATH.exists():
        print("No GitHub issue event payload; nothing to apply.")
        return 0
    event = load(EVENT_PATH, {})
    issue = event.get("issue") or {}
    body = issue.get("body") or ""
    marker = MARKER_RE.search(body)
    if not marker:
        print("Issue is not a publication-review issue; nothing to apply.")
        return 0
    key = marker.group(1).strip()

    label_names = {label.get("name", "") for label in issue.get("labels", [])}
    if REVIEW_LABEL not in label_names:
        print("Publication-review label is absent; nothing to apply.")
        return 0

    topic_config = load(TOPICS, {"labels": {}, "overrides": {}, "titleOverrides": {}, "reviewedUntagged": []})
    valid_topics = set(topic_config.get("labels", {}).keys())
    selected = sorted(
        name[len(TOPIC_PREFIX):]
        for name in label_names
        if name.startswith(TOPIC_PREFIX) and name != NO_TOPIC_LABEL and name[len(TOPIC_PREFIX):] in valid_topics
    )
    intentionally_untagged = NO_TOPIC_LABEL in label_names

    # Creating the issue itself adds only `publication-review`; that event should be a no-op.
    if not selected and not intentionally_untagged:
        print("No publication topic label is selected yet; waiting for reviewer input.")
        return 0
    if selected and intentionally_untagged:
        print("Both topic labels and pub:no-topic are selected; topic labels take precedence.")
        intentionally_untagged = False

    pubs_doc = load(PUBS, {"updated": None, "count": 0, "publications": []})
    pubs = pubs_doc.get("publications", [])
    pub = find_pub(pubs, key)
    if pub is None:
        raise SystemExit(f"Could not find publication for review key: {key}")

    # Persist the human review in publication-topics.json.
    topic_config.setdefault("overrides", {})
    topic_config.setdefault("titleOverrides", {})
    reviewed_untagged = set(topic_config.get("reviewedUntagged", []))
    doi = norm_doi(pub.get("doi"))
    title_key = norm_title(pub.get("title"))
    if selected:
        if doi:
            topic_config["overrides"][doi] = selected
        else:
            topic_config["titleOverrides"][title_key] = selected
        reviewed_untagged.discard(key)
    else:
        if doi:
            topic_config["overrides"].pop(doi, None)
        else:
            topic_config["titleOverrides"].pop(title_key, None)
        reviewed_untagged.add(key)
    topic_config["reviewedUntagged"] = sorted(reviewed_untagged)
    save(TOPICS, topic_config)

    # Update the current live record immediately.
    pub["tags"] = selected
    pubs_doc["updated"] = dt.date.today().isoformat()
    pubs_doc["count"] = len(pubs)
    save(PUBS, pubs_doc)

    # Promote the reviewed ORCID item into the durable, human-curated canonical list.
    curated_doc = load(CURATED, {"updated": None, "count": 0, "publications": []})
    curated = curated_doc.get("publications", [])
    curated_pub = find_pub(curated, key)
    if curated_pub is None:
        curated_pub = dict(pub)
        curated.append(curated_pub)
    curated_pub["tags"] = selected
    curated_pub["source"] = "Curated bibliography (human-reviewed)"
    curated_doc["updated"] = dt.date.today().isoformat()
    curated_doc["count"] = len(curated)
    save(CURATED, curated_doc)

    # Rebuild the review queue from the current publication set.
    pending = []
    reviewed_untagged = set(topic_config.get("reviewedUntagged", []))
    for item in pubs:
        if item.get("tags"):
            continue
        item_key = key_for(item)
        if item_key in reviewed_untagged:
            continue
        pending.append({
            "key": item_key,
            "year": item.get("year"),
            "title": item.get("title"),
            "doi": norm_doi(item.get("doi")) or None,
        })
    pending.sort(key=lambda x: ((x.get("year") or 0), x.get("title") or ""), reverse=True)
    save(REVIEW, {"count": len(pending), "items": pending})

    subprocess.run([sys.executable, str(BUILD)], check=True)
    print(f"Applied publication review for {pub.get('title')}: {selected if selected else ['intentionally untagged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
