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


def author_line(pub: dict) -> str:
    """Extract the author portion of a citation for compact homepage display."""
    citation = str(pub.get("citation") or "").strip()
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
    if pub.get("url"):
        return str(pub["url"])
    if pub.get("doi"):
        return f"https://doi.org/{norm_doi(pub['doi'])}"
    if pub.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{pub['pmid']}/"
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
        f'<p class="pub-citation">{highlight_self(pub.get("citation") or "")}</p>'
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


def scholarly_item(pub: dict, position: int) -> dict:
    item = {
        "@type": "ScholarlyArticle",
        "headline": pub.get("title"),
        "datePublished": str(pub.get("year")) if pub.get("year") else None,
        "author": {"@id": "https://flo-doo.github.io/#florence-doo"},
    }
    url = pub_url(pub)
    if url:
        item["url"] = url
    if pub.get("doi"):
        item["identifier"] = f"https://doi.org/{norm_doi(pub['doi'])}"
    item = {k: v for k, v in item.items() if v not in (None, "")}
    return {"@type": "ListItem", "position": position, "item": item}


def main() -> None:
    data = json.loads(PUBS.read_text(encoding="utf-8"))
    cfg = json.loads(TOPICS.read_text(encoding="utf-8"))
    labels = cfg.get("labels", {})
    pubs = list(data.get("publications") or [])
    for p in pubs:
        p["_tags"] = effective_tags(p, cfg)
    pubs.sort(key=lambda p: ((p.get("year") or 0), p.get("title") or ""), reverse=True)

    # Homepage: static latest publications and static publication count.
    index = INDEX.read_text(encoding="utf-8")
    lastmod = str(data.get("updated") or dt.date.today().isoformat())
    index = re.sub(
        r'("dateModified"\s*:\s*")[0-9]{4}-[0-9]{2}-[0-9]{2}(" )?',
        lambda m: m.group(1) + lastmod + (m.group(2) or ""),
        index,
        count=1,
    )
    index = re.sub(
        r'(<strong id="publication-count">).*?(</strong>)',
        rf'\g<1>{len(pubs)}\2',
        index,
        count=1,
        flags=re.S,
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
    print(f"Built static HTML for {len(pubs)} publications; sitemap lastmod={lastmod}.")


if __name__ == "__main__":
    main()
