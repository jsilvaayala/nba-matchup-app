import sqlite3

import pandas as pd

NBA_TEAMS = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SA", "TOR", "UTAH", "WSH",
}
GAME_TYPES = ("regular-season", "post-season", "play-in-season")

START_RATING = 1500
K = 20            # how fast ratings react to results
HOME_ADV = 100    # Elo points of home-court advantage
CARRYOVER = 0.75  # share of a rating kept from one season to the next


def win_prob(elo_diff):
    return 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))


def load_games(db_path="data/nba.db"):
    conn = sqlite3.connect(db_path)
    games = pd.read_sql(
        """
        SELECT g.game_id, g.game_date, g.season, g.season_type,
               h.abbreviation AS home, a.abbreviation AS away,
               g.home_score, g.away_score
        FROM games g
        JOIN teams h ON h.team_id = g.home_team_id
        JOIN teams a ON a.team_id = g.away_team_id
        WHERE g.season_type IN ('regular-season', 'post-season', 'play-in-season')
          AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
          AND g.season IS NOT NULL
        ORDER BY g.game_date, g.game_id
        """,
        conn,
    )
    conn.close()
    games = games[games["home"].isin(NBA_TEAMS) & games["away"].isin(NBA_TEAMS)]
    games = games.reset_index(drop=True)
    games["season"] = games["season"].astype(int)
    return games


def offseason_regress(ratings, carry=CARRYOVER):
    return {t: START_RATING + carry * (r - START_RATING) for t, r in ratings.items()}


def compute_elo(games):
    """Walk through games in date order. Each prediction uses only earlier games."""
    ratings = {}
    rows = []
    last_season = None
    for g in games.itertuples(index=False):
        if last_season is not None and g.season != last_season:
            ratings = offseason_regress(ratings)
        last_season = g.season

        r_home = ratings.get(g.home, START_RATING)
        r_away = ratings.get(g.away, START_RATING)
        diff = r_home + HOME_ADV - r_away
        p_home = win_prob(diff)
        home_win = 1 if g.home_score > g.away_score else 0

        rows.append((g.game_id, g.game_date, g.season, g.season_type,
                     g.home, g.away, p_home, home_win))

        margin = abs(g.home_score - g.away_score)
        winner_diff = diff if home_win else -diff
        mult = ((margin + 3) ** 0.8) / (7.5 + 0.006 * winner_diff)
        delta = K * mult * (home_win - p_home)
        ratings[g.home] = r_home + delta
        ratings[g.away] = r_away - delta

    history = pd.DataFrame(
        rows,
        columns=["game_id", "game_date", "season", "season_type",
                 "home", "away", "p_home", "home_win"],
    )
    return ratings, history
