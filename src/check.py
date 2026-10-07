import sqlite3

conn = sqlite3.connect("data/nba.db")

print("Games by season / type:")
for row in conn.execute("""
    SELECT season, season_type, COUNT(*), MIN(substr(game_date, 1, 10)), MAX(substr(game_date, 1, 10))
    FROM games GROUP BY season, season_type ORDER BY season, season_type
"""):
    print(" ", row)

print("\nTable row counts:")
for t in ["teams", "players", "games", "team_game_stats", "player_game_stats", "predictions"]:
    try:
        print(" ", t, conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    except Exception as e:
        print(" ", t, "(missing)")
