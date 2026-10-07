import sqlite3

import pandas as pd
import streamlit as st

DB = "data/nba.db"

st.set_page_config(page_title="NBA Matchups", layout="wide")


@st.cache_data
def load_averages():
    conn = sqlite3.connect(DB)
    df = pd.read_sql(
        """
        SELECT p.player_id, p.name, g.season, g.season_type,
               COUNT(*) AS gp,
               AVG(s.minutes) AS mpg,
               AVG(s.pts) AS ppg,
               AVG(s.reb) AS rpg,
               AVG(s.ast) AS apg,
               AVG(s.stl) AS spg,
               AVG(s.blk) AS bpg,
               AVG(s.tov) AS topg,
               SUM(s.fgm) * 1.0 / NULLIF(SUM(s.fga), 0) AS fg_pct,
               SUM(s.fg3m) * 1.0 / NULLIF(SUM(s.fg3a), 0) AS fg3_pct,
               SUM(s.pts) * 1.0 / NULLIF(2 * (SUM(s.fga) + 0.44 * SUM(s.fta)), 0) AS ts_pct
        FROM player_game_stats s
        JOIN players p ON p.player_id = s.player_id
        JOIN games g ON g.game_id = s.game_id
        GROUP BY p.player_id, g.season, g.season_type
        HAVING SUM(s.minutes) > 0
        """,
        conn,
    )
    conn.close()
    return df


def season_label(s):
    return f"{s - 1}-{str(s)[2:]}"


st.title("NBA Player vs. Player")
df = load_averages()

c1, c2, c3 = st.columns(3)
season = c1.selectbox("Season", sorted(df["season"].unique(), reverse=True), format_func=season_label)
types = sorted(df[df["season"] == season]["season_type"].unique())
default_idx = types.index("regular-season") if "regular-season" in types else 0
stype = c2.selectbox("Season type", types, index=default_idx)
min_games = c3.slider("Minimum games played", 1, 20, 3)

pool = df[(df["season"] == season) & (df["season_type"] == stype) & (df["gp"] >= min_games)]
pool = pool.sort_values("ppg", ascending=False)

if pool.empty:
    st.warning("No players match these filters. Try lowering the minimum games.")
    st.stop()

names = pool["name"].tolist()
a_col, b_col = st.columns(2)
p1 = a_col.selectbox("Player A", names, index=0)
p2 = b_col.selectbox("Player B", names, index=min(1, len(names) - 1))

stat_cols = ["gp", "mpg", "ppg", "rpg", "apg", "spg", "bpg", "topg", "fg_pct", "fg3_pct", "ts_pct"]
chosen = pool[pool["name"].isin([p1, p2])].drop_duplicates("name").set_index("name")
table = chosen[stat_cols].T.round(3)

left, right = st.columns(2)
with left:
    st.subheader("Per-game and shooting")
    st.dataframe(table, use_container_width=True)
with right:
    st.subheader("Production comparison")
    st.bar_chart(table.loc[["ppg", "rpg", "apg", "spg", "bpg"]])

st.caption("Stats computed from games stored in my own database. TS% = points / (2 x (FGA + 0.44 x FTA)).")