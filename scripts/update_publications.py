#!/usr/bin/env python3
"""Refresh public publication metadata while preserving the curated CV-based index.

Sources attempted:
  1. ORCID public works endpoint
  2. ORCID public works-page JSON endpoint
  3. Crossref author search as a secondary discovery source

The script never deletes the existing cache when a network source fails. Existing
curated topic tags are preserved. It uses only the Python standard library.
"""
from __future__ import annotations
import json, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

ORCID = "0000-0001-6519-5222"
ROOT = Path(__file__).resolve().parents[1]
PUBS = ROOT / "data" / "publications.json"
TOPICS = ROOT / "data" / "publication-topics.json"
REVIEW = ROOT / "data" / "publication-topic-review.json"
UA = "florence-doo-site/1.0 (mailto:fdoo@som.umaryland.edu)"


def get_json(url: str, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def norm_doi(s: str | None) -> str:
    if not s: return ""
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", s.strip(), flags=re.I).lower().rstrip(".")


def load_existing():
    if not PUBS.exists(): return []
    return json.loads(PUBS.read_text(encoding="utf-8")).get("publications", [])


def load_topic_config():
    try:
        cfg=json.loads(TOPICS.read_text(encoding="utf-8"))
    except Exception:
        cfg={}
    return {
        "labels": cfg.get("labels", {}),
        "overrides": {k.lower(): v for k, v in cfg.get("overrides", {}).items()},
        "titleOverrides": cfg.get("titleOverrides", {}),
        "reviewedUntagged": set(cfg.get("reviewedUntagged", [])),
    }


def topic_key(p):
    d=norm_doi(p.get("doi"))
    return f"doi:{d}" if d else f"title:{norm_title(p.get('title'))}"


def apply_topic_overrides(items):
    cfg=load_topic_config()
    for p in items:
        d=norm_doi(p.get("doi"))
        explicit=cfg["overrides"].get(d) if d else None
        if explicit is None:
            explicit=cfg["titleOverrides"].get(norm_title(p.get("title")))
        p["topics"]=explicit or []
    return items


def write_topic_review(items):
    cfg=load_topic_config()
    review=[]
    for p in items:
        if p.get("topics"):
            continue
        key=topic_key(p)
        if key in cfg["reviewedUntagged"]:
            continue
        review.append({
            "key": key,
            "year": p.get("year"),
            "title": p.get("title"),
            "doi": norm_doi(p.get("doi")) or None,
        })
    review.sort(key=lambda x: ((x.get("year") or 0), x.get("title") or ""), reverse=True)
    REVIEW.write_text(json.dumps({"count": len(review), "items": review}, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return review


def parse_orcid_group(group):
    summaries=group.get("work-summary") or group.get("workSummary") or []
    if not summaries: return None
    w=summaries[0]
    title=((w.get("title") or {}).get("title") or {}).get("value") or ""
    year=(((w.get("publication-date") or {}).get("year") or {}).get("value"))
    try: year=int(year) if year else None
    except: year=None
    doi=pmid=None
    for eid in (group.get("external-ids") or {}).get("external-id", []) or []:
        typ=(eid.get("external-id-type") or "").lower()
        val=eid.get("external-id-value")
        if typ=="doi" and val: doi=norm_doi(val)
        if typ in ("pmid","pubmed") and val: pmid=str(val)
    url=(f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None))
    return {"title":title,"year":year,"doi":doi or None,"pmid":pmid,"url":url,"citation":title,"source":"ORCID","topics":[]}


def fetch_orcid():
    errors=[]
    # Official public API can require credentials in some configurations; try it first.
    try:
        d=get_json(f"https://pub.orcid.org/v3.0/{ORCID}/works", "application/vnd.orcid+json")
        groups=d.get("group", [])
        out=[parse_orcid_group(g) for g in groups]
        return [x for x in out if x and x.get("title")], "ORCID API"
    except Exception as e:
        errors.append(str(e))
    # Public web record endpoint fallback.
    try:
        d=get_json(f"https://orcid.org/{ORCID}/worksPage.json")
        groups=d.get("groups") or d.get("group") or []
        out=[]
        for g in groups:
            # worksPage format differs from API; collect title and external ids defensively.
            ws=g.get("works") or g.get("work-summary") or []
            if not ws: continue
            w=ws[0]
            title=w.get("title") or w.get("workTitle") or ""
            if isinstance(title, dict): title=title.get("value") or title.get("title") or ""
            if isinstance(title, dict): title=title.get("value") or ""
            year=w.get("publicationDate") or w.get("publication-date") or w.get("year")
            if isinstance(year, dict):
                year=((year.get("year") or {}).get("value") if isinstance(year.get("year"),dict) else year.get("year")) or year.get("value")
            try: year=int(str(year)[:4]) if year else None
            except: year=None
            doi=pmid=None
            ext=g.get("externalIdentifiers") or g.get("external-ids") or []
            if isinstance(ext, dict): ext=ext.get("external-id") or []
            for e in ext:
                typ=(e.get("type") or e.get("external-id-type") or "").lower()
                val=e.get("value") or e.get("external-id-value")
                if typ=="doi" and val: doi=norm_doi(str(val))
                if typ in ("pmid","pubmed") and val: pmid=str(val)
            if title:
                out.append({"title":title,"year":year,"doi":doi or None,"pmid":pmid,"url":f"https://doi.org/{doi}" if doi else None,"citation":title,"source":"ORCID","topics":[]})
        return out, "ORCID web record"
    except Exception as e:
        errors.append(str(e))
    print("ORCID unavailable:", " | ".join(errors), file=sys.stderr)
    return [], None


def fetch_crossref():
    params=urllib.parse.urlencode({"query.author":"Florence X Doo","rows":100,"select":"DOI,title,published-print,published-online,issued,container-title,author,URL"})
    try:
        d=get_json("https://api.crossref.org/works?"+params)
    except Exception as e:
        print("Crossref unavailable:", e, file=sys.stderr); return []
    out=[]
    for w in d.get("message",{}).get("items",[]):
        authors=w.get("author") or []
        if not any((a.get("family") or "").lower()=="doo" for a in authors): continue
        title=(w.get("title") or [""])[0]
        doi=norm_doi(w.get("DOI"))
        date=(w.get("published-print") or w.get("published-online") or w.get("issued") or {}).get("date-parts", [[None]])
        year=date[0][0] if date and date[0] else None
        journal=(w.get("container-title") or [""])[0]
        citation=(title + (f". {journal}." if journal else "")).strip()
        out.append({"title":title,"year":year,"doi":doi or None,"pmid":None,"url":f"https://doi.org/{doi}" if doi else w.get("URL"),"citation":citation,"source":"Crossref","topics":[]})
    return out


def merge(existing, discovered):
    by_doi={norm_doi(p.get("doi")):p for p in existing if norm_doi(p.get("doi"))}
    by_title={norm_title(p.get("title")):p for p in existing if p.get("title")}
    items=list(existing)
    for n in discovered:
        keyd=norm_doi(n.get("doi")); keyt=norm_title(n.get("title"))
        old=(by_doi.get(keyd) if keyd else None) or by_title.get(keyt)
        if old:
            # Enrich without replacing curated citation/topics.
            for k in ("year","doi","pmid","url"):
                if not old.get(k) and n.get(k): old[k]=n[k]
            if old.get("source","" ).startswith("CV") and n.get("source"):
                old["source"] = old["source"] + " + " + n["source"]
        else:
            n.setdefault("topics",[])
            items.append(n)
            if keyd: by_doi[keyd]=n
            if keyt: by_title[keyt]=n
    # Deduplicate again.
    seen=set(); result=[]
    for p in items:
        k=norm_doi(p.get("doi")) or norm_title(p.get("title"))
        if not k or k in seen: continue
        seen.add(k); result.append(p)
    return result


def main():
    existing=load_existing()
    orcid, source=fetch_orcid()
    crossref=fetch_crossref()
    merged=merge(existing, orcid+crossref)
    merged=apply_topic_overrides(merged)
    merged.sort(key=lambda p: (p.get("year") or 0, p.get("title") or ""), reverse=True)
    out={"updated":__import__('datetime').date.today().isoformat(),"count":len(merged),"publications":merged}
    PUBS.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    review=write_topic_review(merged)
    print(f"Wrote {len(merged)} publications ({len(existing)} cached, {len(orcid)} ORCID, {len(crossref)} Crossref).")
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build_site.py')], check=True)
    if review:
        print(f"Topic review needed for {len(review)} publication(s). See data/publication-topic-review.json.")

if __name__=="__main__": main()
