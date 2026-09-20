# Site maintenance

## Normal update workflow

From the repository in VS Code:

```powershell
git pull --rebase origin main
git add .
git commit -m "Update personal website"
git push origin main
```

Pull first because the weekly publication workflow can create a remote commit.

## Upcoming appearances

Edit `data/events.json`. The homepage shows the next five future external appearances; `appearances.html` shows the full list in date order.

## Publication categories

`data/publication-topics.json` contains the public labels and DOI-based topic overrides. A publication can have more than one research topic.

Topic keys:
- `trustworthy-human-ai`
- `frontier-clinical-intelligence`
- `sustainable-ai-radiology`
- `medical-imaging-informatics-data`

## Publication refresh

The repository includes a weekly GitHub Action. To refresh locally:

```powershell
python scripts/update_publications.py
```

The updater preserves the curated CV-based cache and tries ORCID and Crossref for new public works. It never intentionally deletes the cache when a network source is unavailable.

## Portrait and affiliation logos

- `assets/images/florence-doo.jpg`
- `assets/images/umsom-logo-white.png`
- `assets/images/umihc-logo-white.png`

## Appearances

`data/events.json` powers both the homepage upcoming list and `appearances.html`. Future events are shown under Upcoming; past curated events appear under Selected prior appearances and can be filtered by `scope` (`institutional`, `national`, `international`).

## Affiliation logos

Dark mode uses `*-logo-white.png`; light mode uses `*-logo-color.png`. Keep both variants when updating institutional branding.
