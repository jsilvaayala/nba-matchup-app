import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.elo import (  # noqa: E402
    HOME_ADV, NBA_TEAMS, START_RATING, compute_elo, load_games,
    offseason_regress, win_prob,
)

DB_PATH = ROOT / "data" / "nba.db"
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
MODEL = "elo_v1"
REAL_TYPES = {"regular-season", "post-season", "play-in-season"}


def ensure_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            game_id TEXT NOT NULL,
            model TEXT NOT NULL,
            season INTEGER,
            season_type TEXT,
            game_date TEXT,
            home TEXT,
            away TEXT,
            p_home REAL,
            logged_at TEXT,
            PRIMARY KEY (game_id, model)
        )
        """
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-ahead", type=int, default=1,
                        help="also look this many days ahead of today")
    parser.add_argument("--include-preseason", action="store_true",
                        help="also log preseason games (for testing the pipeline)")
    args = parser.parse_args()

    games = load_games(str(DB_PATH))
    ratings, _ = compute_elo(games)
    last_season = int(games["season"].max())

    allowed = set(REAL_TYPES)
    if args.include_preseason:
        allowed.add("preseason")

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    seen = new = already = 0
    for offset in range(args.days_ahead + 1):
        d = date.today() + timedelta(days=offset)
        resp = requests.get(
            f"{BASE}/scoreboard",
            params={"dates": d.strftime("%Y%m%d"), "limit": 100},
            headers=HEADERS, timeout=30,
        )
        resp.raise_for_status()
        for ev in resp.json().get("events", []):
            seen += 1
            if ev["status"]["type"]["state"] != "pre":
                continue  # already started or finished: never log after tip-off
            season = ev.get("season", {})
            stype = season.get("slug")
            year = season.get("year")
            if stype not in allowed:
                continue
            comp = ev["competitions"][0]
            home = next(c for c in comp["competitors"] if c["homeAway"] == "home")["team"]["abbreviation"]
            away = next(c for c in comp["competitors"] if c["homeAway"] == "away")["team"]["abbreviation"]
            if home not in NBA_TEAMS or away not in NBA_TEAMS:
                continue

            r = offseason_regress(ratings) if (year and year > last_season) else ratings
            diff = r.get(home, START_RATING) + HOME_ADV - r.get(away, START_RATING)
            p_home = win_prob(diff)

            cur = conn.execute(
                "INSERT OR IGNORE INTO predictions "
                "(game_id, model, season, season_type, game_date, home, away, p_home, logged_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ev["id"], MODEL, year, stype, ev["date"], home, away, p_home, now),
            )
            if cur.rowcount:
                new += 1
                print(f"  logged: {away} @ {home} ({stype}) -> {home} win prob {p_home:.1%}")
            else:
                already += 1

    conn.commit()
    conn.close()
    print(f"\nSaw {seen} games on the scoreboard. Logged {new} new picks, {already} were already logged.")


if __name__ == "__main__":
    main()
