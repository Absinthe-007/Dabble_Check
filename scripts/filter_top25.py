#!/usr/bin/env python3
"""Drop college-football picks whose team is not in data/cfb_top25.json. Run before every push."""
import json, pathlib
d = pathlib.Path(__file__).resolve().parent.parent / "data"
top = json.loads((d / "cfb_top25.json").read_text())["teams"]
ok = {x.upper() for t in top for x in [t["name"], *t["aliases"]]}
picks = json.loads((d / "picks.json").read_text())
keep = [p for p in picks if p.get("sport") != "cfb" or str(p.get("team", "")).strip(". ").upper() in ok]
(d / "picks.json").write_text(json.dumps(keep, indent=1, ensure_ascii=False) + "\n")
print(f"removed {len(picks)-len(keep)} unranked CFB picks; {len(keep)} remain")
