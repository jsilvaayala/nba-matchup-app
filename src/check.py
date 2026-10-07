import sqlite3

conn = sqlite3.connect("data/nba.db")

print("Games by season / type:")
for row in conn.execute(
    "SELECT season, season_type, COUNT(*) FROM games GROUP BY season, season_type ORDER BY season, season_type"
):
    print(" ", row)

print("\nTable row counts:")
for t in ["teams", "players", "games", "team_game_stats", "player_game_stats"]:
    print(" ", t, conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

print("\nMost recent games:")
for row in conn.execute("""
    SELECT substr(g.game_date, 1, 10), a.abbreviation, g.away_score,
           h.abbreviation, g.home_score, g.season_type
    FROM games g
    JOIN teams h ON h.team_id = g.home_team_id
    JOIN teams a ON a.team_id = g.away_team_id
    ORDER BY g.game_date DESC LIMIT 10
"""):
    print(" ", row)