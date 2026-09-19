# Florence X. Doo — personal research site

Static GitHub Pages site for Florence X. Doo, MD, MA.

## Site structure

- `index.html` — homepage
- `publications.html` — searchable publication record
- `assets/styles.css` — site design
- `assets/site.js` — publication rendering/search
- `data/publications.json` — cached publication metadata
- `scripts/update_publications.py` — Crossref/ORCID refresh script
- `.github/workflows/update-publications.yml` — weekly publication refresh

## Research architecture

1. Trustworthy Human–AI Systems
2. Frontier Clinical Intelligence
3. Sustainable AI & Medical Imaging

Clinical AI innovation and translation is presented as a cross-cutting capability rather than a fourth research pillar.

## GitHub Pages

Recommended repository name: `flo-doo.github.io` so the site lives at `https://flo-doo.github.io/`.

The site has no build dependency: GitHub Pages can serve the repository directly from the `main` branch/root directory.

## Publication updates

The scheduled workflow queries Crossref for DOI metadata associated with ORCID `0000-0001-6519-5222` and merges it with curated records already in `data/publications.json`. This prevents transient API failures or incomplete ORCID tagging from deleting older entries.
