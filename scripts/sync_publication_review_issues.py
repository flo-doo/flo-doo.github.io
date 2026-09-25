#!/usr/bin/env python3
"""Keep GitHub publication-review issues aligned with the pending review queue.

Unresolved publications have one open issue. Selecting a `pub:` decision label
resolves the issue automatically; if an unresolved issue is manually closed, the
daily sync reopens it. Historical issues remain as an audit trail.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data" / "publication-topic-review.json"
TOPICS = ROOT / "data" / "publication-topics.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "")
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "")

REVIEW_LABEL = "publication-review"
TOPIC_PREFIX = "pub:"
NO_TOPIC_LABEL = "pub:no-topic"
MARKER_RE = re.compile(r"<!--\s*publication-review-key:(.*?)\s*-->")
TITLE_RE = re.compile(r"^\*\*Title:\*\*\s*(.+?)\s*$", re.M)
DOI_RE = re.compile(r"^\*\*DOI:\*\*\s*`([^`]+)`\s*$", re.M)


def gh(*args: str, capture: bool = False) -> str:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=capture)
    return result.stdout if capture else ""


def ensure_labels(labels: dict[str, str]) -> None:
    specs = [
        (REVIEW_LABEL, "BFDADC", "New ORCID publication needs research-area review"),
        (NO_TOPIC_LABEL, "B7B7B7", "Keep this publication intentionally untagged"),
    ]
    colors = ["1D76DB", "5319E7", "0E8A16", "006B75"]
    for idx, (slug, display) in enumerate(labels.items()):
        specs.append((f"{TOPIC_PREFIX}{slug}", colors[idx % len(colors)], display))
    for name, color, description in specs:
        gh(
            "label", "create", name,
            "--repo", REPO,
            "--color", color,
            "--description", description[:100],
            "--force",
        )


def marker(key: str) -> str:
    return f"<!-- publication-review-key:{key} -->"


def marker_key(body: str) -> str | None:
    match = MARKER_RE.search(body or "")
    return match.group(1).strip() if match else None


def norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def norm_doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value).strip(), flags=re.I).lower().rstrip(".")


def issue_title(body: str) -> str:
    match = TITLE_RE.search(body or "")
    return match.group(1).strip() if match else ""


def issue_doi(body: str) -> str:
    match = DOI_RE.search(body or "")
    return norm_doi(match.group(1)) if match else ""


def label_names(issue: dict) -> set[str]:
    return {label.get("name", "") for label in issue.get("labels", [])}


def has_decision(issue: dict, valid_topics: set[str]) -> bool:
    names = label_names(issue)
    return NO_TOPIC_LABEL in names or any(
        name.startswith(TOPIC_PREFIX)
        and name != NO_TOPIC_LABEL
        and name[len(TOPIC_PREFIX):] in valid_topics
        for name in names
    )


def issue_body(item: dict, labels: dict[str, str]) -> str:
    lines = [
        marker(item["key"]),
        "A new publication was detected from Florence Doo's ORCID record and needs a research-area classification.",
        "",
        f"**Title:** {item.get('title') or ''}",
        f"**Year:** {item.get('year') or ''}",
    ]
    if item.get("doi"):
        lines.append(f"**DOI:** `{item['doi']}`")
    lines += [
        "",
        "### Select the research area",
        "Use the **Labels** control in the issue sidebar to choose one or more of these labels:",
        "",
    ]
    for slug, display in labels.items():
        lines.append(f"- `{TOPIC_PREFIX}{slug}` — {display}")
    lines += [
        f"- `{NO_TOPIC_LABEL}` — intentionally leave this publication untagged",
        "",
        "Selecting a research-area label (or `pub:no-topic`) updates the site and closes this issue automatically.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    if not REPO:
        raise SystemExit("GITHUB_REPOSITORY is required")
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {"items": []}
    topic_config = json.loads(TOPICS.read_text(encoding="utf-8"))
    labels = topic_config.get("labels", {})
    valid_topics = set(labels.keys())
    ensure_labels(labels)

    # Scan all issues rather than filtering by publication-review label. Historical
    # review issues may have had that label removed during manual cleanup.
    issues = json.loads(
        gh(
            "issue", "list", "--repo", REPO, "--state", "all", "--limit", "300",
            "--json", "number,title,body,state,labels", capture=True,
        ) or "[]"
    )

    by_key: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    by_doi: dict[str, dict] = {}
    for issue in issues:
        body = issue.get("body") or ""
        key = marker_key(body)
        if not key:
            continue
        by_key[key] = issue
        title_key = norm_title(issue_title(body))
        doi = issue_doi(body)
        if title_key:
            by_title[title_key] = issue
        if doi:
            by_doi[doi] = issue

    pending = {item["key"]: item for item in review.get("items", [])}
    created = 0
    reopened = 0
    closed = 0
    matched_issue_numbers: set[int] = set()

    for key, item in pending.items():
        existing = by_key.get(key)
        if existing is None and item.get("doi"):
            existing = by_doi.get(norm_doi(item.get("doi")))
        if existing is None and item.get("title"):
            existing = by_title.get(norm_title(item.get("title")))
        if existing:
            if existing.get("number") is not None:
                matched_issue_numbers.add(int(existing["number"]))
            decided = has_decision(existing, valid_topics)
            state = str(existing.get("state", "")).upper()
            if decided and state == "OPEN":
                gh("issue", "close", str(existing["number"]), "--repo", REPO)
                closed += 1
            elif not decided and state == "CLOSED":
                gh("issue", "reopen", str(existing["number"]), "--repo", REPO)
                reopened += 1
            continue

        title = f"Publication review: {item.get('year') or ''} — {item.get('title') or ''}"
        if len(title) > 245:
            title = title[:242] + "..."
        body = issue_body(item, labels)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(body)
            body_path = handle.name
        args = [
            "issue", "create", "--repo", REPO,
            "--title", title,
            "--body-file", body_path,
            "--label", REVIEW_LABEL,
        ]
        if OWNER:
            args += ["--assignee", OWNER]
        gh(*args)
        Path(body_path).unlink(missing_ok=True)
        created += 1

    # Anything no longer in the pending queue is resolved or obsolete.
    for key, issue in by_key.items():
        number = issue.get("number")
        if key in pending or (number is not None and int(number) in matched_issue_numbers):
            continue
        if str(issue.get("state", "")).upper() == "OPEN":
            gh("issue", "close", str(issue["number"]), "--repo", REPO)
            closed += 1

    print(
        f"Publication-review issues: {created} created, {reopened} reopened, "
        f"{closed} closed, {len(pending)} pending."
    )


if __name__ == "__main__":
    main()
