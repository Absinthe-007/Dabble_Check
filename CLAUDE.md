# Dabble Prop Board — standing rules

- **College football: AP Top 25 teams only.** Never write picks for a player whose team is unranked. Before each run, refresh `data/cfb_top25.json` from the latest AP poll (rank, name, aliases/abbreviations as used in the `team` field).
- Also delete any existing unranked CFB picks from the artifact database, not just the export.
- **Before every push to the site**, run `python3 scripts/filter_top25.py` after copying `weeks.json`/`picks.json` into `data/`. Only push if it runs clean.
- Push data to `main` directly (no PR).
- **Schedule: daily at 4:30 AM** (owner's request). Treat Mondays as the build day; every other day (incl. Tue/Wed/Fri/Sat) use the refresh path: grade finished games, fill lines, update news, merge/refresh history. Grade only from box scores you can verify; if a result can't be confirmed, leave the pick pending.
- **Up/down arrows:** the page shows ▲/▼ next to each projection (vs the reference line when numeric, otherwise vs the More/Less direction). When a refresh changes a projection, store the old value in `projPrev` ({value, at}) so the UI can show the move.
- **Sources:** the cloud environment's network proxy blocks nearly every sports/odds site (ESPN, Covers, Action Network, OddsShark, RotoWire, FantasyPros, PFR, CBS, SI, MLB.com, NBC Sports, Bleacher Report, NCAA.com, etc.). WebSearch snippets work. Never bypass blocks. Wider coverage needs the org's allowed-domains list expanded (Admin settings → Capabilities).
