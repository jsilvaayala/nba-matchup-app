import argparse
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "nba.db"
SCHEMA_PATH = ROOT / "src" / "schema.sql"

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
PAUSE = 0.4  # seconds between requests, to be polite

TEAM_COLS = ["game_id", "team_id", "home_away", "pts", "opp_pts", "win",
             "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb",
             "ast", "stl", "blk", "tov", "pf", "pts_in_paint", "fast_break_pts"]
PLAYER_COLS = ["game_id", "player_id", "team_id", "starter", "minutes", "pts",
               "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "ast", "tov",
               "stl", "blk", "oreb", "dreb", "pf", "plus_minus"]
GAME_COLS = ["game_id", "game_date", "season", "season_type",
             "home_team_id", "away_team_id", "home_score", "away_score"]


def get_json(url, params=None, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            time.sleep(PAUSE)
            return r.json()
        except Exception as e:
            print(f"   retry {attempt}: {e}")
            time.sleep(3 * attempt)
    return None


def to_int(value):
    try:
        return int(str(value).replace("+", ""))
    except (ValueError, TypeError):
        return None


def split_made_att(text):
    try:
        made, att = str(text).split("-")
        return int(made), int(att)
    except (ValueError, TypeError):
        return None, None


def upsert(conn, table, cols, row):
    placeholders = ", ".join(":" + c for c in cols)
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def parse_team_stats(stat_list):
    s = {x.get("name"): x.get("displayValue") for x in stat_list}
    fgm, fga = split_made_att(s.get("fieldGoalsMade-fieldGoalsAttempted"))
    fg3m, fg3a = split_made_att(s.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
    ftm, fta = split_made_att(s.get("freeThrowsMade-freeThrowsAttempted"))
    return {
        "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta,
        "oreb": to_int(s.get("offensiveRebounds")),
        "dreb": to_int(s.get("defensiveRebounds")),
        "reb": to_int(s.get("totalRebounds")),
        "ast": to_int(s.get("assists")),
        "stl": to_int(s.get("steals")),
        "blk": to_int(s.get("blocks")),
        "tov": to_int(s.get("turnovers")),
        "pf": to_int(s.get("fouls")),
        "pts_in_paint": to_int(s.get("pointsInPaint")),
        "fast_break_pts": to_int(s.get("fastBreakPoints")),
    }


def process_game(conn, event):
    game_id = event["id"]
    comp = event["competitions"][0]
    competitors = {c["team"]["id"]: c for c in comp["competitors"]}
    home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
    away = next(c for c in comp["competitors"] if c["homeAway"] == "away")

    summ = get_json(f"{BASE}/summary", {"event": game_id})
    if not summ:
        return False
    box = summ.get("boxscore", {})
    if not box.get("teams") or not box.get("players"):
        return False

    season = event.get("season", {})
    season_type = season.get("slug") or str(season.get("type", "unknown"))

    for c in comp["competitors"]:
        t = c["team"]
        conn.execute(
            "INSERT OR REPLACE INTO teams (team_id, abbreviation, name) VALUES (?, ?, ?)",
            (t["id"], t.get("abbreviation"), t.get("displayName")),
        )

    upsert(conn, "games", GAME_COLS, {
        "game_id": game_id, "game_date": event["date"],
        "season": season.get("year"), "season_type": season_type,
        "home_team_id": home["team"]["id"], "away_team_id": away["team"]["id"],
        "home_score": to_int(home.get("score")), "away_score": to_int(away.get("score")),
    })

    for t in box["teams"]:
        tid = t["team"]["id"]
        me = competitors.get(tid)
        if me is None:
            continue
        opp = away if me is home else home
        row = {
            "game_id": game_id, "team_id": tid, "home_away": me["homeAway"],
            "pts": to_int(me.get("score")), "opp_pts": to_int(opp.get("score")),
            "win": 1 if me.get("winner") else 0,
        }
        row.update(parse_team_stats(t.get("statistics", [])))
        upsert(conn, "team_game_stats", TEAM_COLS, row)

    for tb in box["players"]:
        tid = tb["team"]["id"]
        for grp in tb.get("statistics", [])[:1]:
            labels = grp.get("labels", [])
            for a in grp.get("athletes", []):
                stats = a.get("stats", [])
                if not stats or len(stats) != len(labels):
                    continue  # did not play
                d = dict(zip(labels, stats))
                fgm, fga = split_made_att(d.get("FG"))
                fg3m, fg3a = split_made_att(d.get("3PT"))
                ftm, fta = split_made_att(d.get("FT"))
                athlete = a["athlete"]
                conn.execute(
                    "INSERT OR REPLACE INTO players (player_id, name) VALUES (?, ?)",
                    (athlete["id"], athlete.get("displayName")),
                )
                upsert(conn, "player_game_stats", PLAYER_COLS, {
                    "game_id": game_id, "player_id": athlete["id"], "team_id": tid,
                    "starter": 1 if a.get("starter") else 0,
                    "minutes": to_int(d.get("MIN")), "pts": to_int(d.get("PTS")),
                    "fgm": fgm, "fga": fga, "fg3m": fg3m, "fg3a": fg3a,
                    "ftm": ftm, "fta": fta,
                    "reb": to_int(d.get("REB")), "ast": to_int(d.get("AST")),
                    "tov": to_int(d.get("TO")), "stl": to_int(d.get("STL")),
                    "blk": to_int(d.get("BLK")), "oreb": to_int(d.get("OREB")),
                    "dreb": to_int(d.get("DREB")), "pf": to_int(d.get("PF")),
                    "plus_minus": to_int(d.get("+/-")),
                })

    conn.commit()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-10-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--days", type=int, default=None,
                        help="only re-check the last N days (for daily updates)")
    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    if args.days is not None:
        start = end - timedelta(days=args.days)
    else:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()

    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    total_new = 0
    d = start
    while d <= end:
        data = get_json(f"{BASE}/scoreboard", {"dates": d.strftime("%Y%m%d"), "limit": 100})
        events = data.get("events", []) if data else []
        new = 0
        for ev in events:
            completed = ev.get("status", {}).get("type", {}).get("completed", False)
            if not completed:
                continue
            exists = conn.execute("SELECT 1 FROM games WHERE game_id = ?", (ev["id"],)).fetchone()
            if exists:
                continue
            try:
                if process_game(conn, ev):
                    new += 1
            except Exception as e:
                conn.rollback()
                print(f"   skipped game {ev.get('id')}: {type(e).__name__}: {e}")
        if events:
            print(f"{d}: {len(events)} games on scoreboard, {new} new")
        total_new += new
        d += timedelta(days=1)

    conn.close()
    print(f"\nDone. {total_new} new games saved.")


if __name__ == "__main__":
    main()