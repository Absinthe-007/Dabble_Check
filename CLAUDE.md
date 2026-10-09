# Dabble Prop Board — standing rules

- **College football: AP Top 25 teams only.** Never write picks for a player whose team is unranked. Before each run, refresh `data/cfb_top25.json` from the latest AP poll (rank, name, aliases/abbreviations as used in the `team` field).
- Also delete any existing unranked CFB picks from the artifact database, not just the export.
- **Before every push to the site**, run `python3 scripts/filter_top25.py` after copying `weeks.json`/`picks.json` into `data/`. Only push if it runs clean.
- Push data to `main` directly (no PR).
- **Schedule: daily at 4:30 AM** (owner's request). Treat Mondays as the build day; every other day (incl. Tue/Wed/Fri/Sat) use the refresh path: grade finished games, fill lines, update news, merge/refresh history. Grade only from box scores you can verify; if a result can't be confirmed, leave the pick pending.
- **Up/down arrows:** the page shows ▲/▼ next to each projection (vs the reference line when numeric, otherwise vs the More/Less direction). When a refresh changes a projection, store the old value in `projPrev` ({value, at}) so the UI can show the move.
- **Network:** the routine's cloud environment has Full network access (owner switched it on Oct 6, 2026). ESPN, CBS, Covers, Action Network, RotoWire, FantasyPros, BettingPros, VegasInsider, PFF, NFL.com, MLB.com, Daily Faceoff, StatMuse, Basketball-Reference and sportsbook pages all load, so read the full pages, not just search snippets. Some sites still refuse automated requests (e.g. Pro-Football-Reference, The Athletic): skip those and use other sources. Never bypass paywalls, logins or bot blocks.

## Coverage: more players, every prop type (owner's request, Oct 6 2026)
- Cover every game on the slate in each in-season sport, and go deep on each game: aim for **6–12 props per NFL game, 4–8 per Top 25 CFB game, 4–8 per NHL game, 6–10 per NBA/WNBA game**, covering both teams.
- Use the full range of prop types, not just yards and points. Every sport should show a real mix:
  - **NFL / CFB:** passing yds, completions, attempts, pass TDs, INTs thrown, rushing yds/attempts, receiving yds, receptions, longest reception, rush+rec yds, **tackles, solo tackles, tackles+assists, sacks, defensive INTs**, kicking points/FGs made.
  - **NHL:** shots on goal, points, goals, assists, **blocked shots, hits**, power-play points, goalie saves (confirmed starters only).
  - **NBA / WNBA:** points, **rebounds, assists, blocks, steals, blocks+steals**, threes made, turnovers, PRA, pts+reb, pts+ast, reb+ast.
- Write the `stat` field with these exact names (e.g. "Blocked shots", "Tackles + assists", "Blocks + steals") so the site's stat-type filters group them.
- The volume target never overrides the grounding rules: every prop still needs a projection with a real numeric basis, sources, and a confirmed active player. Defensive and role-player props are fine at confidence 2.

## Sources: every conceivable source (owner's request — the more the better)
Before writing or refreshing any pick, search widely across all of these, for every game and every player you write about:
- **Official / team:** league and official injury reports, practice participation reports, team announcements and press releases, team websites and team social accounts (as quoted in coverage), depth charts, transactions/roster moves, IR/IL designations, probable pitchers, confirmed starting goalies, starting lineups.
- **News & insiders:** national outlets, local papers, beat writers, insider reports, press-conference quotes from coaches and players.
- **Rumors:** trade and roster rumors, lineup leaks, workload/snap-count chatter. Always label a rumor as a rumor in `analysis` (who reported it, how solid it is) and never treat it as settled.
- **Injuries:** injury reports, injury-analysis sites, return timelines, players listed questionable/doubtful/GTD and how that shifts usage for teammates.
- **Betting:** sportsbooks and pick'em apps (lines and line movement), odds aggregators, prop analysts and prop-pick articles, public-betting and sharp-money reports, projections sites.
- **Grades & analytics:** player and unit grades, advanced stats, matchup ratings, defense-vs-position rankings, usage/snap/target/shot shares, game logs, splits, pace and weather.
- **Anything else reputable you can reach.** More sources is better.

How: run many WebSearch queries per game and per player (injury news, team announcements, "player props", beat-writer notes, grades, line movement, rumors), and try WebFetch on every promising result. When a page is blocked, use the search-result snippet and move on. Never bypass paywalls, logins, robots blocks, geo-blocks or the network proxy. Add every page relied on to the pick's `sources` and the week's `sources` list, and fold grades/insight you find into `analysis`, `matchup` and the projection `basis`.

## Site layout
- `index.html` has stat-type filter chips built from each pick's `stat` value, a More/Less filter, a team filter and sorting. Keep the data fields it reads: `stat`, `side`, `projection{value,basis}`, `projPrev`, `position`, `team`, `game`, `gameTime`, `startTime`, `confidence`, `condition`, `analysis`, `projLine`, `matchup`, `teamOutlook`, `history`, `bio`, `sources`.
- Lines stay hidden on cards (the owner asked for More/Less + projection); a numeric `line` only feeds the projection arrow and grade.

## Reporting: hit rate by sport (owner's request, Oct 7 2026)
- In every update's notification, break the hit rate down per sport (NFL, CFB, NHL, WNBA): W-L and % for the games graded that run, and the season-to-date total from all graded picks in the database. Exclude voids and pending picks from the percentage, and say how many were voided.
- The site's top scoreboard (`renderRecord` in `index.html`) shows overall hit rate, record, and each sport's W-L and hit % across all graded picks in `data/picks.json`, so it updates on every push. Never drop graded picks from earlier weeks from the export; they feed this record.

## Live tracking (owner's request, Oct 7 2026)
- `live.js` polls ESPN's public scoreboard/box-score feeds in the visitor's browser and shows a LIVE/FINAL line with the player's running stat on open picks. It never changes saved results; grading still happens in the daily run. It matches picks by `espnId` (or player name), `game` ("AWAY @ HOME" abbreviations), `startTime` and the exact `stat` names above, so keep those fields accurate. Props it can't read from a box score (e.g. NHL power-play points) just show the game status.
- The "Games & players" section lists every game on today's slate (all sports, live/upcoming/final). Expanding a game loads both teams' full rosters from ESPN and merges in live box-score stats, flagging starters where ESPN provides them (WNBA), injury designations, and any open picks on that player for that game. It is view-only and independent of which players have picks.

## MLB removed (owner's request, Oct 7 2026)
- MLB is gone: all MLB picks (open and graded) and MLB news were deleted from the artifact database, and the site no longer lists it. Never create, refresh, grade or report MLB picks; do not run MLB research or an MLB builder, and leave MLB out of the notification's per-sport hit rate.
- If any `mlb` docs show up in an export, delete them from the database; `scripts/build_data.py` also filters them out.

## Must plays: 5 per sport (owner's request, Oct 7 2026)
- Every update, pick the 5 strongest open More/Less picks for each in-season sport (NFL, CFB, NHL, WNBA) and store them on the pick docs as `must: {rank: 1-5, note}`. The site shows them as "<Sport> must plays" at the top of that sport's tab (hidden on the All tab); when a sport has no `must` picks it falls back to its 5 best-graded open picks.
- Choose from open picks in games that have not started: confidence 3+ (or a real book line with a clear edge), one pick per player, at most 2 per game, no unresolved injury condition, and the side agreeing with projection vs the line. Prefer picks with real book lines; otherwise a clean numeric basis. The `note` is one or two plain sentences using only facts already in the pick (lines, averages, news); never invent a spread or a stat.
- Clear stale `must` fields from picks that are no longer in the top 5 (set `must` to `{"__delete__": true}`), and re-rank each run.
- Keep the A–F grade on every pick (the site computes it from confidence, projection vs line and any open condition).
- No review step: the owner does not want to preview updates (Oct 7 2026). Every run pushes straight to `main` once `filter_top25.py` runs clean, and the notification reports what changed.

## Depth: positions, history, lines (owner's request, Oct 9 2026)
- Go deeper on every pick: in `analysis`/`matchup`, name the player's position and role (depth-chart spot, line/pairing, snap/TOI share), and how the opposing team's matching position group (e.g. CB room vs this WR, opposing D-pair vs this forward) has been playing; use only facts from the sources.
- `history` should give the last 3–5 game log values for the stat plus the opponent split when available; `projLine` should list the full expected stat line, and `lines` every book line found.
- The "Games & players" rosters are grouped by position (QB/RB/WR/TE/OL/DL/LB/DB/ST, C/W/D/G, G/F/C) in `index.html`; live stats keep polling every 30s while a game is live.
