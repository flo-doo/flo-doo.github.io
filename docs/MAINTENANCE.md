# Site maintenance

## Normal update workflow

From the local `flo-doo.github.io` repository:

```powershell
git add .
git commit -m "Update personal website"
git push origin main
```

GitHub Pages redeploys automatically.

## Upcoming talks

Edit `data/events.json`. The homepage shows the next three future events and stops showing each event after its date passes.

## Portrait

The homepage portrait is `assets/images/florence-doo.jpg`.

## Publications

`data/publications.json` powers both the homepage and the publications browser.

The GitHub Action `.github/workflows/update-publications.yml` runs the updater in `scripts/update_publications.py`. The updater first reads the public works shown on the ORCID record, enriches works with Crossref DOI metadata when available, and merges those results with the existing cached records. This avoids relying only on Crossref's ORCID field, which can omit older publications.

The workflow runs weekly, can be run manually from **GitHub → Actions → Refresh publications → Run workflow**, and also runs when the updater itself changes.
