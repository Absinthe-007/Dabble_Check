#!/usr/bin/env python3
"""Combine an ArtifactData export (out_dir with weeks/ and picks/ folders of
<doc_id>.json files) into data/weeks.json and data/picks.json for the site.

Usage: python3 scripts/build_data.py <export_dir>
"""
import json, sys, pathlib, datetime

src = pathlib.Path(sys.argv[1])
root = pathlib.Path(__file__).resolve().parent.parent
out = root / "data"
out.mkdir(exist_ok=True)

def load(coll):
    docs = []
    for f in sorted((src / coll).glob("*.json")):
        d = json.loads(f.read_text())
        d = {"id": f.stem, **d}
        docs.append(d)
    return docs

weeks = sorted(load("weeks"), key=lambda w: w.get("weekStart", w["id"]), reverse=True)
picks = sorted((p for p in load("picks") if p.get("sport") != "mlb"), key=lambda p: p["id"])  # MLB removed (owner request, Oct 7 2026)
for w in weeks:
    (w.get("news") or {}).pop("mlb", None)
if not weeks:
    sys.exit("No weeks found in export; refusing to overwrite data.")

(out / "weeks.json").write_text(json.dumps(weeks, indent=1, ensure_ascii=False) + "\n")
(out / "picks.json").write_text(json.dumps(picks, indent=1, ensure_ascii=False) + "\n")
(out / "meta.json").write_text(json.dumps({"exportedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           "weeks": len(weeks), "picks": len(picks)}) + "\n")
print(f"wrote {len(weeks)} weeks, {len(picks)} picks")
