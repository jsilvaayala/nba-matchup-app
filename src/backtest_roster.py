import math
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from src.elo import compute_elo, load_games
from src.player_ratings import (
    DECAY, FEATURES, STAGE_A_LAMBDA, box_rates, fit_prior, prior_vector, ridge,
)

DB = "data/nba.db"
LAMBDA = 30       # shrinkage (chosen earlier on this same season: a small leak)
N_RECENT = 15     # lineup = who played for the team in its last 15 games
REFIT_DAYS = 30   # refit ratings about monthly


def build_X(train, by_game_team, pidx):
    X = np.zeros((len(train), len(pidx) + 1))
    for i, g in enumerate(train.itertuples(index=False)):
        for team, sign in ((g.home, 1.0), (g.away, -1.0)):
            for pid, mins in by_game_team.get((g.game_id, team), {}).items():
                j = pidx.get(pid)
                if j is not None:
                    X[i, j] += sign * mins / 48.0
    X[:, -1] = 1.0
    y = (train["home_score"] - train["away_score"]).to_numpy(dtype=float)
    return X, y


def fit_both(train, pl, by_game_team, last):
    """Return (plain_ratings, plain_edge), (boxprior_ratings, boxprior_edge)."""
    pl_tr = pl[pl["game_id"].isin(set(train["game_id"]))]
    pidx = {p: i for i, p in enumerate(sorted(pl_tr["player_id"].unique()))}
    X, y = build_X(train, by_game_team, pidx)
    w = DECAY ** (last - train["season"].to_numpy())

    plain = ridge(X, y, w, LAMBDA)
    rates = box_rates(pl_tr, last)
    beta0 = ridge(X, y, w, STAGE_A_LAMBDA)
    predict, _ = fit_prior(rates, {p: beta0[j] for p, j in pidx.items()})
    prior = prior_vector(predict, rates, pidx)
    boxed = ridge(X, y, w, LAMBDA, prior)

    return (
        ({p: plain[j] for p, j in pidx.items()}, plain[-1]),
        ({p: boxed[j] for p, j in pidx.items()}, boxed[-1]),
    )


def main():
    games = load_games(DB).reset_index(drop=True)
    _, hist = compute_elo(games)
    elo_p = dict(zip(hist["game_id"], hist["p_home"]))

    reg = games[games["season_type"] == "regular-season"].reset_index(drop=True)
    reg["dt"] = pd.to_datetime(reg["game_date"], utc=True)
    last = int(reg["season"].max())

    conn = sqlite3.connect(DB)
    cols = ", ".join(f"s.{c}" for c in FEATURES)
    pl = pd.read_sql(
        f"""
        SELECT s.game_id, s.player_id, t.abbreviation AS team, s.minutes, g.season, {cols}
        FROM player_game_stats s
        JOIN teams t ON t.team_id = s.team_id
        JOIN games g ON g.game_id = s.game_id
        WHERE s.minutes > 0
        """,
        conn,
    )
    conn.close()
    pl = pl[pl["game_id"].isin(set(reg["game_id"]))].copy()
    pl["season"] = pl["season"].astype(int)

    by_game_team = {}
    for r in pl[["game_id", "team", "player_id", "minutes"]].itertuples(index=False):
        by_game_team.setdefault((r.game_id, r.team), {})[r.player_id] = r.minutes

    team_games = {}
    plain = box = None
    next_refit = None

    def strength(team, model):
        ratings = model[0]
        recent = team_games.get(team, [])[-N_RECENT:]
        if not recent:
            return 0.0
        tot = {}
        for gid in recent:
            for pid, m in by_game_team.get((gid, team), {}).items():
                tot[pid] = tot.get(pid, 0.0) + m
        return sum(ratings.get(pid, 0.0) * (m / len(recent)) / 48.0 for pid, m in tot.items())

    rows = []
    for g in reg.itertuples(index=False):
        if g.season == last:
            if next_refit is None or g.dt >= next_refit:
                train = reg[reg["dt"] < g.dt - pd.Timedelta(days=1)]
                plain, box = fit_both(train, pl, by_game_team, last)
                next_refit = g.dt + pd.Timedelta(days=REFIT_DAYS)
            m_plain = strength(g.home, plain) - strength(g.away, plain) + plain[1]
            m_box = strength(g.home, box) - strength(g.away, box) + box[1]
            rows.append((g.game_id, g.dt.strftime("%Y-%m"), m_plain, m_box,
                         g.home_score - g.away_score))
        team_games.setdefault(g.home, []).append(g.game_id)
        team_games.setdefault(g.away, []).append(g.game_id)

    df = pd.DataFrame(rows, columns=["game_id", "month", "m_plain", "m_box", "margin"])
    df["home_win"] = (df["margin"] > 0).astype(int)
    df["p_elo"] = df["game_id"].map(elo_p)
    df = df.dropna(subset=["p_elo"])

    def to_prob(col):
        sigma = float((df["margin"] - df[col]).std())
        return df[col].apply(lambda m: 0.5 * (1 + math.erf(m / (sigma * math.sqrt(2))))), sigma

    df["p_plain"], s1 = to_prob("m_plain")
    df["p_box"], s2 = to_prob("m_box")
    df["p_blend"] = (df["p_elo"] + df["p_box"]) / 2

    def score(p):
        return ((p > 0.5).astype(int) == df["home_win"]).mean(), ((p - df["home_win"]) ** 2).mean()

    base = df["home_win"].mean()
    base_brier = ((base - df["home_win"]) ** 2).mean()
    rmse = lambda c: float(np.sqrt(((df["margin"] - df[c]) ** 2).mean()))

    print(f"Games tested: {len(df)} (season {last - 1}-{str(last)[2:]}, regular season)")
    print(f"Margin error (RMSE, points): home edge only {df['margin'].std():.2f}"
          f" | plain roster {rmse('m_plain'):.2f} | box-prior roster {rmse('m_box'):.2f}\n")
    print(f"{'model':28}{'accuracy':>10}{'Brier':>9}")
    for name, p in [("Elo", df["p_elo"]), ("Roster (plain ratings)", df["p_plain"]),
                    ("Roster (box-prior ratings)", df["p_box"]),
                    ("Average: Elo + box-prior", df["p_blend"])]:
        acc, br = score(p)
        print(f"{name:28}{acc:>10.1%}{br:>9.4f}")
    print(f"{'Home-rate baseline':28}{'':>10}{base_brier:>9.4f}")

    print("\nBrier score by month (lower is better):")
    for month, d in df.groupby("month"):
        hw = d["home_win"]
        f = lambda c: ((d[c] - hw) ** 2).mean()
        print(f"  {month}  n={len(d):3d}  elo {f('p_elo'):.4f}  plain {f('p_plain'):.4f}"
              f"  box {f('p_box'):.4f}  blend {f('p_blend'):.4f}")


if __name__ == "__main__":
    main()
