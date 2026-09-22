#!/usr/bin/env python3
"""Create GitHub review issues for ORCID works that still need topic classification.

The workflow assigns each issue to the repository owner so normal GitHub issue
notifications can deliver an email/push alert. Research-area labels are created
once and then used as the review UI; selecting those labels is handled by
apply_publication_review.py.
"""
from __future__ import annotations

import json
import os
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


def gh(*args: str, capture: bool = False) -> str:
    cmd = ["gh", *args]
    result = subprocess.run(cmd, check=True, text=True, capture_output=capture)
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
        "Each label change is applied to the site automatically. Select all applicable research-area labels, then close this issue when finished.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    if not REPO:
        raise SystemExit("GITHUB_REPOSITORY is required")
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {"items": []}
    topic_config = json.loads(TOPICS.read_text(encoding="utf-8"))
    labels = topic_config.get("labels", {})
    ensure_labels(labels)

    issues = json.loads(
        gh(
            "issue", "list", "--repo", REPO, "--state", "all", "--limit", "200",
            "--label", REVIEW_LABEL, "--json", "number,title,body,state", capture=True,
        ) or "[]"
    )

    by_key: dict[str, dict] = {}
    for issue in issues:
        body = issue.get("body") or ""
        for item in review.get("items", []):
            if marker(item["key"]) in body:
                by_key[item["key"]] = issue

    created = 0
    reopened = 0
    for item in review.get("items", []):
        existing = by_key.get(item["key"])
        if existing:
            if str(existing.get("state", "")).upper() == "CLOSED":
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

    print(f"Publication-review issues: {created} created, {reopened} reopened, {len(review.get('items', []))} pending.")


if __name__ == "__main__":
    main()
