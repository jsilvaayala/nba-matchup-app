import sqlite3

conn = sqlite3.connect("data/nba.db")
rows = conn.execute("""
    SELECT t.abbreviation, COUNT(*) AS games
    FROM team_game_stats s
    JOIN games g ON g.game_id = s.game_id
    JOIN teams t ON t.team_id = s.team_id
    WHERE g.season = 2026 AND g.season_type = 'regular-season'
    GROUP BY t.abbreviation
    ORDER BY games
""").fetchall()

for abbr, n in rows:
    flag = "" if n == 82 else "  <-- check"
    print(f"{abbr:5} {n}{flag}")