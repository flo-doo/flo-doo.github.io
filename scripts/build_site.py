#!/usr/bin/env python3
"""Build SEO-visible static publication content from data/publications.json.

This script keeps the site lightweight while ensuring publication titles,
citations, research tags, and the latest-publications panel are present in the
initial HTML instead of depending on client-side rendering.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBS = ROOT / "data" / "publications.json"
TOPICS = ROOT / "data" / "publication-topics.json"
INDEX = ROOT / "index.html"
PUBLICATIONS = ROOT / "publications.html"
SITEMAP = ROOT / "sitemap.xml"
SITEMAP_TEXT = ROOT / "sitemap.txt"
SITE_META = ROOT / "data" / "site-meta.json"


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def norm_doi(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value


SELF_NAME_RE = re.compile(r"\bDoo\s+F(?:X)?\b", re.I)


def highlight_self(value: str) -> str:
    """Escape text and emphasize Florence Doo author-name variants."""
    value = str(value or "")
    out = []
    last = 0
    for m in SELF_NAME_RE.finditer(value):
        out.append(esc(value[last:m.start()]))
        out.append(f'<span class="self-author">{esc(m.group(0))}</span>')
        last = m.end()
    out.append(esc(value[last:]))
    return "".join(out)



MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
CONTRIBUTION_NOTE_RE = re.compile(
    r"primary draft|supervision|project conceptualization|primary data gathering|"
    r"statistical interpretation|IRB primary investigator|ran analyses|co-wrote|edited primary draft",
    re.I,
)

def clean_citation(value: str) -> str:
    """Remove CV-only contribution annotations while preserving citation/status notes."""
    text = str(value or "").strip()
    while True:
        m = re.search(r"\s*\(([^()]*)\)\s*\.?\s*$", text)
        if not m or not CONTRIBUTION_NOTE_RE.search(m.group(1)):
            break
        text = text[:m.start()].rstrip()
        if text and not text.endswith("."):
            text += "."
    return text

def _date(y: int, m: int = 1, d: int = 1) -> dt.date:
    try:
        return dt.date(int(y), int(m), int(d))
    except Exception:
        return dt.date(int(y), int(m), 1)

def publication_sort_meta(pub: dict) -> tuple[int, dt.date]:
    """Return (accepted/in-press priority, best available publication/acceptance date)."""
    citation = clean_citation(pub.get("citation") or "")
    year = int(pub.get("year") or 0)
    status = str(pub.get("status") or "").lower()
    accepted = status in {"accepted", "in press", "in-press"} or (
        status != "published" and bool(re.search(r"\bAccepted\b|\bin press\b", citation, re.I))
    )
    # 'Epub ahead of print' is a published electronic record, not merely accepted.
    if re.search(r"Epub ahead of print", citation, re.I):
        accepted = False

    explicit = str(pub.get("date") or pub.get("published_date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", explicit):
        try:
            parsed = dt.date.fromisoformat(explicit)
            return (1 if accepted else 0, parsed)
        except ValueError:
            pass

    # Prefer an explicit acceptance date for in-press records.
    if accepted:
        m = re.search(r"Accepted\s+([A-Za-z]+)\s+(\d{1,2})[,]?\s+(\d{4})", citation, re.I)
        if m and m.group(1).lower() in MONTHS:
            return (1, _date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))))
        m = re.search(r"Accepted\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", citation, re.I)
        if m and m.group(2).lower() in MONTHS:
            return (1, _date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))))
        m = re.search(r"Accepted\s+([A-Za-z]+)\s+(\d{4})", citation, re.I)
        if m and m.group(1).lower() in MONTHS:
            return (1, _date(int(m.group(2)), MONTHS[m.group(1).lower()], 1))
        return (1, _date(year or 1900, 12, 31))

    # Common citation forms: 2026 Jul 30; 2026 May; Aug 14 2026; 14 Aug 2026.
    for pat, order in [
        (r"\b(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})\b", "ymd"),
        (r"\b([A-Za-z]+)\s+(\d{1,2})[,]?\s+(\d{4})\b", "mdy"),
        (r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", "dmy"),
    ]:
        m = re.search(pat, citation)
        if not m:
            continue
        try:
            if order == "ymd":
                y, mon, day = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
            elif order == "mdy":
                mon, day, y = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
            else:
                day, mon, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
            return (0, _date(y, mon, day))
        except (KeyError, ValueError):
            pass

    m = re.search(r"\b(\d{4})\s+([A-Za-z]+)\b", citation)
    if m and m.group(2).lower() in MONTHS:
        return (0, _date(int(m.group(1)), MONTHS[m.group(2).lower()], 1))
    m = re.search(r"\b([A-Za-z]+)\s+(\d{4})\b", citation)
    if m and m.group(1).lower() in MONTHS:
        return (0, _date(int(m.group(2)), MONTHS[m.group(1).lower()], 1))
    return (0, _date(year or 1900, 1, 1))

def publication_sort_key(pub: dict):
    priority, parsed = publication_sort_meta(pub)
    return (priority, parsed.toordinal(), str(pub.get("title") or "").casefold())

def author_line(pub: dict) -> str:
    """Extract the author portion of a citation for compact homepage display."""
    citation = clean_citation(pub.get("citation") or "")
    title = str(pub.get("title") or "").strip()
    if not citation:
        return ""
    if title:
        idx = citation.casefold().find(title.casefold())
        if idx > 0:
            return citation[:idx].rstrip(" .\"“”")
    # Fallback: author lists in this dataset precede the first sentence break.
    first = citation.split(". ", 1)[0].strip()
    return first if len(first) <= 500 else ""


def pub_url(pub: dict) -> str:
    """Best available public link: DOI > supplied record > PubMed > Scholar title search."""
    if pub.get("doi"):
        return f"https://doi.org/{norm_doi(pub['doi'])}"
    if pub.get("url"):
        return str(pub["url"])
    if pub.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{pub['pmid']}/"
    title = str(pub.get("title") or "").strip()
    if title:
        from urllib.parse import quote_plus
        return "https://scholar.google.com/scholar?q=" + quote_plus('"' + title + '"')
    return ""


def effective_tags(pub: dict, cfg: dict) -> list[str]:
    doi_key = norm_doi(pub.get("doi"))
    if doi_key and doi_key in cfg.get("overrides", {}):
        return list(cfg["overrides"][doi_key])
    title_key = norm_title(pub.get("title", ""))
    if title_key in cfg.get("titleOverrides", {}):
        return list(cfg["titleOverrides"][title_key])
    return list(pub.get("tags") or pub.get("topics") or [])


def replace_block(text: str, name: str, content: str) -> str:
    start = f"<!-- AUTO:{name}:START -->"
    end = f"<!-- AUTO:{name}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    replacement = f"{start}\n{content.rstrip()}\n{end}"
    if not pattern.search(text):
        raise RuntimeError(f"Missing build markers for {name}")
    return pattern.sub(replacement, text, count=1)


def pub_article(pub: dict, labels: dict[str, str]) -> str:
    tags_list = pub.get("_tags", [])
    tag_html = "".join(f'<span class="pub-tag">{esc(labels[t])}</span>' for t in tags_list if t in labels)
    url = pub_url(pub)
    title = esc(pub.get("title"))
    title_html = f'<a href="{esc(url)}" target="_blank" rel="noreferrer">{title} ↗</a>' if url else title
    ident = pub.get("id") or norm_doi(pub.get("doi")) or norm_title(pub.get("title", ""))[:28]
    ident = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(ident)).strip("-") or "publication"
    data_tags = ",".join(tags_list)
    return (
        f'<article class="pub-item" id="pub-{esc(ident)}" data-tags="{esc(data_tags)}">'
        f'<div class="pub-year"><time datetime="{esc(pub.get("year"))}">{esc(pub.get("year"))}</time></div>'
        f'<div><h2 class="pub-title">{title_html}</h2>'
        f'<p class="pub-citation">{highlight_self(clean_citation(pub.get("citation") or ""))}</p>'
        f'{f"<div class=\"pub-tags\">{tag_html}</div>" if tag_html else ""}'
        f'</div></article>'
    )


def latest_item(pub: dict) -> str:
    url = pub_url(pub)
    year = esc(pub.get("year"))
    title = esc(pub.get("title"))
    authors = author_line(pub)
    authors_html = f'<div class="latest-authors">{highlight_self(authors)}</div>' if authors else ""
    inner = f'<div class="latest-meta">{year}</div><span class="latest-title">{title}</span>{authors_html}'
    if url:
        return f'<a class="latest-item" href="{esc(url)}" target="_blank" rel="noreferrer">{inner}</a>'
    return f'<div class="latest-item">{inner}</div>'


def scholarly_article(pub: dict) -> dict:
    priority, parsed = publication_sort_meta(pub)
    item = {
        "@type": "ScholarlyArticle",
        "headline": pub.get("title"),
        "datePublished": (str(pub.get("year")) if priority else parsed.isoformat()) if pub.get("year") else None,
        "author": {"@id": "https://flo-doo.github.io/#florence-doo"},
    }
    url = pub_url(pub)
    if url:
        item["url"] = url
    if pub.get("doi"):
        item["identifier"] = f"https://doi.org/{norm_doi(pub['doi'])}"
    return {k: v for k, v in item.items() if v not in (None, "")}


def scholarly_item(pub: dict, position: int) -> dict:
    return {"@type": "ListItem", "position": position, "item": scholarly_article(pub)}


def update_profile_jsonld(index: str, lastmod: str, latest_pubs: list[dict]) -> str:
    """Expose recent scholarly work via hasPart; keep ProfilePage dateModified manual."""
    pattern = re.compile(r'(<script type="application/ld\+json">\s*)(\{.*?\})(\s*</script>)', re.S)
    matches = list(pattern.finditer(index))
    for match in matches:
        try:
            schema = json.loads(match.group(2))
        except json.JSONDecodeError:
            continue
        if schema.get("@type") != "ProfilePage":
            continue
        # Google expects ProfilePage.dateModified to be a full ISO 8601 DateTime.
        # Keep that value in index.html as a manual human-edited profile timestamp
        # rather than replacing it with the publication cache's date-only value.
        schema["hasPart"] = [scholarly_article(p) for p in latest_pubs]
        replacement = match.group(1) + json.dumps(schema, ensure_ascii=False, indent=2) + match.group(3)
        return index[:match.start()] + replacement + index[match.end():]
    return index


def main() -> None:
    data = json.loads(PUBS.read_text(encoding="utf-8"))
    cfg = json.loads(TOPICS.read_text(encoding="utf-8"))
    labels = cfg.get("labels", {})
    pubs = list(data.get("publications") or [])
    for p in pubs:
        p["_tags"] = effective_tags(p, cfg)
    pubs.sort(key=publication_sort_key, reverse=True)

    # Homepage: static latest publications and static publication count.
    index = INDEX.read_text(encoding="utf-8")
    site_meta = json.loads(SITE_META.read_text(encoding="utf-8")) if SITE_META.exists() else {}
    candidate_dates = [str(x) for x in (data.get("updated"), site_meta.get("updated")) if x]
    lastmod = max(candidate_dates) if candidate_dates else dt.date.today().isoformat()
    index = update_profile_jsonld(index, lastmod, pubs[:5])
    index = re.sub(
        r'(<strong id="publication-count">).*?(</strong>)',
        rf'\g<1>{len(pubs)}\2',
        index,
        count=1,
        flags=re.S,
    )
    index = re.sub(
        r'(<a href="publications\.html">)All publications(?: \(\d+\))? →(</a>)',
        rf'\g<1>All publications ({len(pubs)}) →\2',
        index,
        count=1,
    )
    latest_html = "\n".join(latest_item(p) for p in pubs[:5])
    index = replace_block(index, "INDEX-LATEST-PUBLICATIONS", latest_html)
    INDEX.write_text(index, encoding="utf-8")

    # Publications page: filters, complete publication list, and scholarly JSON-LD.
    page = PUBLICATIONS.read_text(encoding="utf-8")
    tag_counts = {key: sum(1 for p in pubs if key in p.get("_tags", [])) for key in labels}
    filter_html = [
        f'<a class="topic-filter" href="publications.html" data-topic="all">All <span>{len(pubs)}</span></a>'
    ]
    filter_html += [
        f'<a class="topic-filter" href="publications.html?topic={esc(key)}" data-topic="{esc(key)}">{esc(label)} <span>{tag_counts[key]}</span></a>'
        for key, label in labels.items()
    ]
    page = replace_block(page, "PUBLICATION-FILTERS", "\n".join(filter_html))
    page = re.sub(
        r'(<p id="pub-count" class="pub-count">).*?(</p>)',
        rf'\g<1>{len(pubs)} publications\2',
        page,
        count=1,
        flags=re.S,
    )
    page = replace_block(page, "PUBLICATION-LIST", "\n".join(pub_article(p, labels) for p in pubs))

    schema = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "@id": "https://flo-doo.github.io/publications.html#page",
        "url": "https://flo-doo.github.io/publications.html",
        "isPartOf": {"@id": "https://flo-doo.github.io/#website"},
        "name": "Publications | Florence X. Doo, MD, MA",
        "description": "Publication record for Florence X. Doo, MD, MA, spanning trustworthy human-AI systems, frontier clinical intelligence, sustainable AI and radiology, and medical imaging, informatics, and data systems.",
        "about": {"@id": "https://flo-doo.github.io/#florence-doo"},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(pubs),
            "itemListElement": [scholarly_item(p, i + 1) for i, p in enumerate(pubs)],
        },
    }
    schema_html = '<script type="application/ld+json">\n' + json.dumps(schema, ensure_ascii=False, indent=2) + '\n</script>'
    page = replace_block(page, "PUBLICATIONS-JSONLD", schema_html)
    PUBLICATIONS.write_text(page, encoding="utf-8")

    # Both index and publications change when the publication cache changes.
    sitemap = f'''<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url>\n    <loc>https://flo-doo.github.io/</loc>\n    <lastmod>{esc(lastmod)}</lastmod>\n  </url>\n  <url>\n    <loc>https://flo-doo.github.io/publications.html</loc>\n    <lastmod>{esc(lastmod)}</lastmod>\n  </url>\n</urlset>\n'''
    SITEMAP.write_text(sitemap, encoding="utf-8")
    SITEMAP_TEXT.write_text(
        "https://flo-doo.github.io/\nhttps://flo-doo.github.io/publications.html\n",
        encoding="utf-8",
    )
    print(f"Built static HTML for {len(pubs)} publications; sitemap lastmod={lastmod}.")


if __name__ == "__main__":
    main()
