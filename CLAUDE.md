# Dabble Prop Board — standing rules

- **College football: AP Top 25 teams only.** Never write picks for a player whose team is unranked. Before each run, refresh `data/cfb_top25.json` from the latest AP poll (rank, name, aliases/abbreviations as used in the `team` field).
- Also delete any existing unranked CFB picks from the artifact database, not just the export.
- **Before every push to the site**, run `python3 scripts/filter_top25.py` after copying `weeks.json`/`picks.json` into `data/`. Only push if it runs clean.
- Push data to `main` directly (no PR).
