import sqlite3

import pandas as pd
import streamlit as st

from src.elo import HOME_ADV, compute_elo, load_games, offseason_regress, win_prob

DB = "data/nba.db"

st.set_page_config(page_title="Team vs Team", layout="wide")


def season_label(s):
    return f"{s - 1}-{str(s)[2:]}"


@st.cache_data
def get_elo():
    games = load_games(DB)
    ratings, history = compute_elo(games)
    return ratings, history, int(games["season"].max())


@st.cache_data
def get_names():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT abbreviation, name FROM teams").fetchall()
    conn.close()
    return {a: n for a, n in rows}


@st.cache_data
def get_team_stats(season):
    conn = sqlite3.connect(DB)
    df = pd.read_sql(
        """
        SELECT t.abbreviation AS team,
               COUNT(*) AS gp,
               SUM(s.win) AS wins,
               AVG(s.pts) AS ppg,
               AVG(s.opp_pts) AS opp_ppg,
               SUM(s.fgm) * 1.0 / SUM(s.fga) AS fg_pct,
               SUM(s.fg3m) * 1.0 / SUM(s.fg3a) AS fg3_pct,
               SUM(s.fg3a) * 1.0 / SUM(s.fga) AS fg3_rate,
               AVG(s.reb) AS rpg,
               AVG(s.ast) AS apg,
               AVG(s.tov) AS topg,
               AVG(s.pts_in_paint) AS paint_pts,
               AVG(s.fast_break_pts) AS fastbreak_pts,
               SUM(s.pts) AS pts_sum,
               SUM(s.opp_pts) AS opp_sum,
               SUM(s.fga - s.oreb + s.tov + 0.44 * s.fta) AS poss
        FROM team_game_stats s
        JOIN games g ON g.game_id = s.game_id
        JOIN teams t ON t.team_id = s.team_id
        WHERE g.season = ? AND g.season_type = 'regular-season'
        GROUP BY t.abbreviation
        """,
        conn,
        params=(int(season),),
    )
    conn.close()
    df["pace"] = df["poss"] / df["gp"]
    df["off_rtg"] = 100 * df["pts_sum"] / df["poss"]
    df["def_rtg"] = 100 * df["opp_sum"] / df["poss"]
    df["net_rtg"] = df["off_rtg"] - df["def_rtg"]
    return df.set_index("team")


@st.cache_data
def get_head_to_head(a, b):
    conn = sqlite3.connect(DB)
    df = pd.read_sql(
        """
        SELECT substr(g.game_date, 1, 10) AS date, g.season_type,
               h.abbreviation AS home, a.abbreviation AS away,
               g.home_score, g.away_score
        FROM games g
        JOIN teams h ON h.team_id = g.home_team_id
        JOIN teams a ON a.team_id = g.away_team_id
        WHERE g.season_type IN ('regular-season', 'post-season', 'play-in-season')
          AND ((h.abbreviation = ? AND a.abbreviation = ?)
            OR (h.abbreviation = ? AND a.abbreviation = ?))
        ORDER BY g.game_date DESC
        """,
        conn,
        params=(a, b, b, a),
    )
    conn.close()
    return df


ratings, history, last_season = get_elo()
names = get_names()
teams = sorted(ratings.keys())


def fmt(t):
    return f"{t} - {names.get(t, t)}"


st.title("NBA Team vs. Team")

c1, c2, c3 = st.columns(3)
team_a = c1.selectbox("Team A", teams, index=0, format_func=fmt)
team_b = c2.selectbox("Team B", teams, index=1, format_func=fmt)
home = c3.selectbox("Home team", [team_a, team_b], index=0, format_func=fmt)

if team_a == team_b:
    st.warning("Pick two different teams.")
    st.stop()

season_complete = (history["season"] == last_season).sum() >= 1200
if season_complete:
    project = st.checkbox(
        f"Project ratings into {season_label(last_season + 1)} "
        "(pulls every team 25% toward average, as Elo models do each offseason)",
        value=True,
    )
else:
    project = False
if project:
    ratings = offseason_regress(ratings)

away = team_b if home == team_a else team_a
diff = ratings[home] + HOME_ADV - ratings[away]
p_home = win_prob(diff)
margin = diff / 28.0  # roughly 28 Elo points per point of margin

st.subheader("Matchup prediction")
m1, m2, m3, m4 = st.columns(4)
m1.metric(f"{team_a} Elo", f"{ratings[team_a]:.0f}")
m2.metric(f"{team_b} Elo", f"{ratings[team_b]:.0f}")
m3.metric(f"{home} (home) win probability", f"{p_home:.1%}")
if margin >= 0:
    m4.metric("Projected margin", f"{home} by {margin:.1f}")
else:
    m4.metric("Projected margin", f"{away} by {-margin:.1f}")
st.caption(
    "Elo only knows game results. It does not know about trades, injuries, or rest, "
    "so roster changes are not reflected yet."
)

st.subheader("Season comparison")
seasons = sorted(history[history["season_type"] == "regular-season"]["season"].unique(), reverse=True)
season = st.selectbox("Season", seasons, format_func=season_label)
stats = get_team_stats(season)

if team_a not in stats.index or team_b not in stats.index:
    st.info("No regular-season games for one of these teams in that season yet.")
else:
    labels = {
        "gp": "Games", "wins": "Wins", "ppg": "Points per game",
        "opp_ppg": "Opponent points per game", "off_rtg": "Offensive rating (approx)",
        "def_rtg": "Defensive rating (approx)", "net_rtg": "Net rating (approx)",
        "pace": "Pace (approx possessions)", "fg_pct": "FG%", "fg3_pct": "3P%",
        "fg3_rate": "3PA share of shots", "rpg": "Rebounds", "apg": "Assists",
        "topg": "Turnovers", "paint_pts": "Points in the paint",
        "fastbreak_pts": "Fast-break points",
    }
    sub = stats.loc[[team_a, team_b], list(labels.keys())]
    left, right = st.columns(2)
    with left:
        st.dataframe(sub.T.rename(index=labels).round(3), use_container_width=True)
    with right:
        st.bar_chart(sub[["off_rtg", "def_rtg", "net_rtg"]].T.rename(
            index={"off_rtg": "Offense", "def_rtg": "Defense", "net_rtg": "Net"}))

st.subheader("Head to head (games in my database)")
h2h = get_head_to_head(team_a, team_b)
if h2h.empty:
    st.info("No games between these teams in the database.")
else:
    a_wins = (
        ((h2h["home"] == team_a) & (h2h["home_score"] > h2h["away_score"])).sum()
        + ((h2h["away"] == team_a) & (h2h["away_score"] > h2h["home_score"])).sum()
    )
    st.write(f"**{team_a} {a_wins} - {len(h2h) - a_wins} {team_b}** in {len(h2h)} games")
    st.dataframe(h2h, use_container_width=True, hide_index=True)

with st.expander("How good is this model? (backtest)"):
    test = history[(history["season"] == last_season) & (history["season_type"] == "regular-season")]
    if len(test) < 100:
        st.write("Not enough games yet.")
    else:
        acc = ((test["p_home"] > 0.5).astype(int) == test["home_win"]).mean()
        brier = ((test["p_home"] - test["home_win"]) ** 2).mean()
        base_rate = test["home_win"].mean()
        base_brier = ((base_rate - test["home_win"]) ** 2).mean()
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Games tested", len(test))
        b2.metric("Elo accuracy", f"{acc:.1%}")
        b3.metric("Elo Brier score", f"{brier:.4f}")
        b4.metric("Baseline Brier", f"{base_brier:.4f}")
        st.caption(
            f"Season {season_label(last_season)}, regular season. Every prediction uses only "
            "games played before it. Brier score: lower is better. Baseline = always predict "
            f"the home win rate ({base_rate:.1%}). With one season loaded, Elo starts cold at "
            "1500 for every team, so early-season predictions are weak."
        )
