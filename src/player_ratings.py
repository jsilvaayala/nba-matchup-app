import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from src.elo import NBA_TEAMS

DB = "data/nba.db"
DECAY = 0.6            # each older season counts 60% as much as the next
LAMBDAS = [10, 30, 100, 300]
STAGE_A_LAMBDA = 30    # first-pass ratings used to learn the box-score prior
MIN_FOR_PRIOR = 300    # players need this many minutes to help fit the prior
PSEUDO_MIN = 500       # shrinks low-minute stat lines toward league average
FEATURES = ["pts", "fga", "fta", "fg3m", "oreb", "dreb", "ast", "stl", "blk", "tov", "pf"]
SANITY = ["Nikola Jokic", "Shai Gilgeous-Alexander", "Giannis Antetokounmpo",
          "Luka Doncic", "Stephen Curry", "Victor Wembanyama", "Kevin Huerter"]


def load():
    conn = sqlite3.connect(DB)
    marks = ",".join("?" * len(NBA_TEAMS))
    games = pd.read_sql(
        f"""
        SELECT g.game_id, g.season, g.home_team_id, g.away_team_id,
               g.home_score, g.away_score
        FROM games g
        JOIN teams h ON h.team_id = g.home_team_id
        JOIN teams a ON a.team_id = g.away_team_id
        WHERE g.season_type = 'regular-season'
          AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
          AND h.abbreviation IN ({marks}) AND a.abbreviation IN ({marks})
        ORDER BY g.game_date
        """,
        conn,
        params=list(NBA_TEAMS) * 2,
    )
    cols = ", ".join(f"s.{c}" for c in FEATURES)
    players = pd.read_sql(
        f"SELECT s.game_id, s.player_id, s.team_id, s.minutes, {cols} "
        "FROM player_game_stats s WHERE s.minutes > 0",
        conn,
    )
    names = dict(conn.execute("SELECT player_id, name FROM players").fetchall())
    return conn, games, players, names


def build(games, players, pidx):
    pl = players[players["game_id"].isin(set(games["game_id"]))]
    gidx = {g: i for i, g in enumerate(games["game_id"])}
    home = dict(zip(games["game_id"], games["home_team_id"]))
    X = np.zeros((len(games), len(pidx) + 1))
    for r in pl.itertuples(index=False):
        j = pidx.get(r.player_id)
        if j is None:
            continue
        sign = 1.0 if r.team_id == home[r.game_id] else -1.0
        X[gidx[r.game_id], j] += sign * r.minutes / 48.0
    X[:, -1] = 1.0  # home-court edge
    y = (games["home_score"] - games["away_score"]).to_numpy(dtype=float)
    return X, y


def ridge(X, y, w, lam, prior=None):
    """Ridge regression that shrinks toward `prior` (zeros if none given)."""
    if prior is None:
        prior = np.zeros(X.shape[1])
    Xw = X * w[:, None]
    A = X.T @ Xw
    pen = np.full(X.shape[1], float(lam))
    pen[-1] = 0.0  # never shrink the home-court term
    A += np.diag(pen)
    delta = np.linalg.solve(A, Xw.T @ (y - X @ prior))
    return prior + delta


def box_rates(pl, ref):
    """Per-36 stat rates, older seasons discounted, thin samples pulled to average."""
    w = DECAY ** (ref - pl["season"].to_numpy())
    d = pd.DataFrame({"player_id": pl["player_id"].to_numpy(),
                      "m": pl["minutes"].to_numpy() * w})
    for c in FEATURES:
        d[c] = pl[c].fillna(0).to_numpy() * w
    g = d.groupby("player_id").sum()
    league = g[FEATURES].sum() / g["m"].sum()
    out = g[FEATURES].add(league * PSEUDO_MIN, axis=1).div(g["m"] + PSEUDO_MIN, axis=0) * 36
    out["minutes"] = pl.groupby("player_id")["minutes"].sum()
    return out


def fit_prior(rates, rating):
    fit = rates[(rates["minutes"] >= MIN_FOR_PRIOR) & rates.index.isin(list(rating.keys()))]
    F = fit[FEATURES]
    mu, sd = F.mean(), F.std().replace(0, 1)
    Z = np.column_stack([((F - mu) / sd).to_numpy(), np.ones(len(F))])
    y = np.array([rating[p] for p in fit.index])
    w = fit["minutes"].to_numpy()
    w = w / w.mean()
    A = Z.T @ (Z * w[:, None]) + np.diag([2.0] * len(FEATURES) + [0.0])
    coef = np.linalg.solve(A, Z.T @ (w * y))

    def predict(all_rates):
        Za = np.column_stack([((all_rates[FEATURES] - mu) / sd).to_numpy(),
                              np.ones(len(all_rates))])
        return pd.Series(np.clip(Za @ coef, -4, 4), index=all_rates.index)

    return predict, dict(zip(FEATURES, coef[:-1]))


def prior_vector(predict, rates, pidx):
    series = predict(rates)
    prior = np.zeros(len(pidx) + 1)
    for pid, j in pidx.items():
        prior[j] = series.get(pid, 0.0)
    return prior


def main():
    conn, games, players, names = load()
    games = games.reset_index(drop=True)
    games["season"] = games["season"].astype(int)
    last = int(games["season"].max())
    pl = players.merge(games[["game_id", "season"]], on="game_id")
    print(f"Games used: {len(games)} (seasons {games['season'].min()} to {last})")

    train = games[games["season"] < last].reset_index(drop=True)
    test = games[games["season"] == last].reset_index(drop=True)
    tr_pl = pl[pl["season"] < last]
    pidx = {p: i for i, p in enumerate(sorted(tr_pl["player_id"].unique()))}
    Xtr, ytr = build(train, pl, pidx)
    Xte, yte = build(test, pl, pidx)
    w = DECAY ** (last - 1 - train["season"].to_numpy())

    rates = box_rates(tr_pl, last - 1)
    beta0 = ridge(Xtr, ytr, w, STAGE_A_LAMBDA)
    predict, _ = fit_prior(rates, {p: beta0[j] for p, j in pidx.items()})
    prior = prior_vector(predict, rates, pidx)

    def rmse(beta):
        return float(np.sqrt(np.mean((yte - Xte @ beta) ** 2)))

    print("\nPredicting last season's margins (RMSE in points, lower is better):")
    print(f"  home edge only:                  {np.sqrt(np.mean((yte - ytr.mean()) ** 2)):.2f}")
    for lam in LAMBDAS:
        print(f"  old method (start at 0), lam={lam:<4} {rmse(ridge(Xtr, ytr, w, lam)):.2f}")
    results = {"box score only": rmse(ridge(Xtr, ytr, w, 1e6, prior))}
    for lam in LAMBDAS:
        results[lam] = rmse(ridge(Xtr, ytr, w, lam, prior))
    print(f"  box score profile only:          {results['box score only']:.2f}")
    for lam in LAMBDAS:
        print(f"  box prior + lineups, lam={lam:<4}   {results[lam]:.2f}")
    best_lam = min(LAMBDAS, key=lambda k: results[k])
    print(f"Using box prior + lineups with lambda = {best_lam}")
    print("(Uses actual minutes played, so this shows the ratings carry signal; the")
    print(" pre-game backtest comes next.)")

    # Final fit on all seasons
    all_pl = pl
    pidx = {p: i for i, p in enumerate(sorted(all_pl["player_id"].unique()))}
    X, y = build(games, pl, pidx)
    w = DECAY ** (last - games["season"].to_numpy())
    rates = box_rates(all_pl, last)
    beta0 = ridge(X, y, w, STAGE_A_LAMBDA)
    predict, coefs = fit_prior(rates, {p: beta0[j] for p, j in pidx.items()})
    prior = prior_vector(predict, rates, pidx)
    beta = ridge(X, y, w, best_lam, prior)
    print(f"\nHome-court edge: {beta[-1]:.2f} points")
    print("What the box-score prior learned (standardized weights, per-36 stats):")
    for k, v in sorted(coefs.items(), key=lambda kv: -abs(kv[1])):
        print(f"  {k:5} {v:+.2f}")

    recent_min = pl[pl["season"] == last].groupby("player_id")["minutes"].sum()
    conn.execute("DROP TABLE IF EXISTS player_ratings")
    conn.execute("CREATE TABLE player_ratings (player_id TEXT PRIMARY KEY, name TEXT, "
                 "rating REAL, recent_minutes REAL)")
    rows = [(pid, names.get(pid), float(beta[j]), float(recent_min.get(pid, 0.0)))
            for pid, j in pidx.items()]
    conn.executemany("INSERT INTO player_ratings VALUES (?, ?, ?, ?)", rows)
    conn.commit()

    df = pd.DataFrame(rows, columns=["player_id", "name", "rating", "recent_minutes"])
    top = df[df["recent_minutes"] >= 800].sort_values("rating", ascending=False).reset_index(drop=True)
    print("\nTop 25 players (at least 800 minutes last season):")
    for i, r in top.head(25).iterrows():
        print(f"  {i + 1:2}. {r['name']:28} {r['rating']:6.2f}   ({int(r['recent_minutes'])} min)")
    print("\nBottom 5:")
    for _, r in top.tail(5).iterrows():
        print(f"      {r['name']:28} {r['rating']:6.2f}   ({int(r['recent_minutes'])} min)")
    print(f"\nSanity check, rank among {len(top)} players:")
    for nm in SANITY:
        hit = top.index[top["name"] == nm]
        if len(hit):
            print(f"  {nm:28} #{hit[0] + 1}")
    print(f"\nSaved {len(rows)} player ratings to the player_ratings table.")
    conn.close()


if __name__ == "__main__":
    main()
