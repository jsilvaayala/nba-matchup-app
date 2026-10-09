import csv
import sqlite3

conn = sqlite3.connect("data/nba.db")
rows = conn.execute(
    """
    SELECT game_id, model, season, season_type, game_date, home, away, p_home, logged_at
    FROM predictions
    ORDER BY logged_at, game_id
    """
).fetchall()
conn.close()

with open("data/predictions.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["game_id", "model", "season", "season_type", "game_date",
                "home", "away", "p_home", "logged_at"])
    w.writerows(rows)

print(f"Exported {len(rows)} picks to data/predictions.csv")
