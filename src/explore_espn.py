import json
from pathlib import Path

import requests

Path("data/raw").mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"

# 1) A day's scoreboard
sb = requests.get(f"{BASE}/scoreboard", params={"dates": "20251022"}, headers=HEADERS, timeout=30).json()
Path("data/raw/scoreboard_sample.json").write_text(json.dumps(sb, indent=2))

events = sb.get("events", [])
print("Games found:", len(events))
ev = events[0]
print("First game:", ev["id"], ev["name"], ev["date"])
for c in ev["competitions"][0]["competitors"]:
    print("  ", c["homeAway"], c["team"]["abbreviation"], "score:", c.get("score"), "winner:", c.get("winner"))

# 2) That game's box score
summ = requests.get(f"{BASE}/summary", params={"event": ev["id"]}, headers=HEADERS, timeout=30).json()
Path("data/raw/summary_sample.json").write_text(json.dumps(summ, indent=2))

print("\nSummary keys:", list(summ.keys()))
box = summ.get("boxscore", {})
print("Boxscore keys:", list(box.keys()))

for t in box.get("teams", []):
    stats = [f'{s.get("name")}={s.get("displayValue")}' for s in t.get("statistics", [])]
    print("\nTeam", t["team"]["abbreviation"], "stats:", stats)

for p in box.get("players", []):
    grp = p["statistics"][0]
    print("\nPlayers for", p["team"]["abbreviation"])
    print("  labels:", grp.get("labels"))
    a = grp["athletes"][0]
    print("  example:", a["athlete"]["displayName"], "| id", a["athlete"]["id"], "| stats", a["stats"])