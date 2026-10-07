# Dabble Prop Board

Weekly player-prop leans (More/Less) for NFL, college football, NHL, NBA and WNBA, built from the past week's news.

- `index.html` — the site (static; reads `data/*.json`)
- `data/weeks.json`, `data/picks.json` — the board data, refreshed every Monday and Thursday by a Claude scheduled task
- `scripts/build_data.py` — turns the weekly database export into those JSON files
- `scripts/props/` — stat-based prop builders that fill games up to the per-game targets in `CLAUDE.md`

## Prop builders
The builders turn public stat feeds into pick docs with every field the site reads. Inputs and output go to `.props-work/` (git-ignored); set `PROPS_WORK`, `PROPS_TODAY` or `PROPS_WEEK` to override.

1. Export the pick database into `.props-work/export/` (ArtifactData `list` with `out_dir`, collections `picks` and `weeks`).
2. `python3 scripts/props/fetch_inputs.py` — the week's slate (ESPN), NHL stats/injuries/goalies, WNBA injuries.
3. Run the builders. Each one counts the picks a game already has, adds props up to the target and continues the pick numbering:
   - `nhl_build.py 2026-10-07 2026-10-08` — dates to fill (target 4). Saves props only for goalies Daily Faceoff lists as confirmed today.
   - `wnba_build.py <eventId>:<prevEventId>:<label>:<target>` — ESPN event ids.
   - `fb_build.py nfl 6` / `fb_build.py cfb 4` — every unstarted game; CFB props only for Top 25 teams in `data/cfb_top25.json`.
4. Review `.props-work/new/<sport>/*.json`, write them to the database (ArtifactData `batch`), then export and run `build_data.py` and `filter_top25.py` as usual.

The builders use no book lines: `line` stays null, and each lean is measured against the half-point nearest the player's season average, which the analysis says. They do not read news, so add injury or role context by hand when it matters.

## Hosting
Settings → Pages → Deploy from branch → `main` / root. The site appears at
`https://<username>.github.io/dabble-prop-board/`.

Lines are reference lines from news coverage; Dabble's own lines can differ. Analysis, not guarantees.
