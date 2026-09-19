# Florence X. Doo — Personal Research Site

A deliberately minimal GitHub Pages site organized around four homepage sections:

1. Hero / research identity
2. Three research pillars with selected work
3. Current activity (upcoming talks + latest publications)
4. About / professional profiles

## Portrait

Add the final portrait as:

`assets/images/florence-doo.jpg`

Do **not** place image files in `data/`.

## Upcoming talks

Edit `data/events.json`. Example:

```json
{
  "events": [
    {
      "date": "2026-10-08",
      "title": "Invited talk title",
      "event": "Conference or institution",
      "location": "City, State",
      "url": "https://example.org/event"
    }
  ]
}
```

The homepage automatically shows the next three future events and stops showing them after their date passes.

## Publications

`data/publications.json` powers the homepage latest-publications list and the publications browser. The scheduled GitHub Action in `.github/workflows/update-publications.yml` refreshes publication metadata.

## Design

The site intentionally uses a single system sans-serif stack:

`Aptos → Segoe UI Variable → Segoe UI → Helvetica Neue → Arial`

This avoids external font dependencies and preserves an Aptos-like visual tone across Windows, macOS, and mobile devices.
