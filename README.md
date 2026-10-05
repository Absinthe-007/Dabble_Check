# Dabble Prop Board

Weekly player-prop leans (More/Less) for NFL, college football, MLB and NBA, built from the past week's news.

- `index.html` — the site (static; reads `data/*.json`)
- `data/weeks.json`, `data/picks.json` — the board data, refreshed every Monday and Thursday by a Claude scheduled task
- `scripts/build_data.py` — turns the weekly database export into those JSON files

## Hosting
Settings → Pages → Deploy from branch → `main` / root. The site appears at
`https://<username>.github.io/dabble-prop-board/`.

Lines are reference lines from news coverage; Dabble's own lines can differ. Analysis, not guarantees.
