import sqlite3
import sys

import requests

sys.path.insert(0, ".")
from src.elo import NBA_TEAMS

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

conn = sqlite3.connect("data/nba.db")
rows = conn.execute("SELECT team_id, abbreviation FROM teams").fetchall()
conn.close()

shown_keys = False
for tid, abbr in sorted(rows, key=lambda r: r[1] or ""):
    if abbr not in NBA_TEAMS:
        continue
    resp = requests.get(f"{BASE}/teams/{tid}/roster", headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(abbr, "HTTP", resp.status_code)
        continue
    data = resp.json()
    if not shown_keys:
        print("Top-level keys:", list(data.keys()))
        shown_keys = True
    athletes = data.get("athletes", [])
    if athletes and isinstance(athletes[0], dict) and "items" in athletes[0]:
        athletes = [a for grp in athletes for a in grp["items"]]
    names = [a.get("displayName") for a in athletes]
    print(f"{abbr:5} {len(names):2} players:", names[:5])
