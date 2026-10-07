import sqlite3

import pandas as pd
import streamlit as st

DB = "data/nba.db"

st.set_page_config(page_title="Prediction Tracker", layout="wide")
st.title("Prediction Tracker")
st.write(
    "Every pick below was recorded by a script before tip-off and is never edited. "
    "Scores are filled in automatically after each game."
)


@st.cache_data(ttl=300)
def load_log():
    conn = sqlite3.connect(DB)
    try:
        df = pd.read_sql(
            """
            SELECT p.game_id, p.game_date, p.season_type, p.home, p.away,
                   p.p_home, p.logged_at, g.home_score, g.away_score
            FROM predictions p
            LEFT JOIN games g ON g.game_id = p.game_id
            WHERE p.model = 'elo_v1'
            ORDER BY p.game_date DESC
            """,
            conn,
        )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


log = load_log()
if log.empty:
    st.info("No predictions logged yet. Run  python src/predict.py  in the terminal.")
    st.stop()

show_pre = st.checkbox("Include preseason (test) games", value=False)
if not show_pre:
    log = log[log["season_type"] != "preseason"]
if log.empty:
    st.info("Nothing to show yet. Regular-season picks start on opening night (Oct 20).")
    st.stop()

log = log.copy()
log["date"] = log["game_date"].str[:10]
log["matchup"] = log["away"] + " @ " + log["home"]
log["pre_tip"] = log["logged_at"] < log["game_date"]
log["final"] = log["home_score"].notna()

done = log[log["final"]].copy()
done["home_win"] = (done["home_score"] > done["away_score"]).astype(int)
done["pick"] = done.apply(lambda r: r["home"] if r["p_home"] >= 0.5 else r["away"], axis=1)
done["correct"] = (done["p_home"] > 0.5).astype(int) == done["home_win"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Picks logged", len(log))
m2.metric("Logged before tip-off", f"{int(log['pre_tip'].sum())} of {len(log)}")
m3.metric("Games scored", len(done))
if len(done):
    m4.metric("Pick accuracy", f"{done['correct'].mean():.1%}")

if len(done):
    brier = ((done["p_home"] - done["home_win"]) ** 2).mean()
    base = done["home_win"].mean()
    base_brier = ((base - done["home_win"]) ** 2).mean()
    always_home = done["home_win"].mean()
    b1, b2, b3 = st.columns(3)
    b1.metric("Brier score (lower is better)", f"{brier:.4f}")
    b2.metric("Baseline Brier", f"{base_brier:.4f}")
    b3.metric("'Always pick home' accuracy", f"{always_home:.1%}")
    if len(done) < 50:
        st.caption("Small sample: these numbers will swing a lot until a few hundred games are scored.")

if len(done) >= 50:
    st.subheader("Calibration: when the model says X%, how often does it happen?")
    done["bucket"] = pd.cut(done["p_home"], [0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0])
    cal = done.groupby("bucket", observed=True).agg(
        games=("home_win", "size"),
        predicted=("p_home", "mean"),
        actual=("home_win", "mean"),
    )
    cal.index = cal.index.astype(str)
    st.dataframe(cal.round(3), use_container_width=True)
    st.line_chart(cal[["predicted", "actual"]])

upcoming = log[~log["final"]]
if len(upcoming):
    st.subheader("Upcoming picks")
    up = upcoming[["date", "matchup", "p_home"]].copy()
    up["home win prob"] = (up["p_home"] * 100).round(1).astype(str) + "%"
    st.dataframe(up[["date", "matchup", "home win prob"]], use_container_width=True, hide_index=True)

if len(done):
    st.subheader("Scored picks")
    out = done[["date", "matchup", "p_home", "pick", "home_score", "away_score", "correct"]].copy()
    out["home win prob"] = (out["p_home"] * 100).round(1).astype(str) + "%"
    out["final"] = out["away_score"].astype(int).astype(str) + " - " + out["home_score"].astype(int).astype(str)
    st.dataframe(
        out[["date", "matchup", "home win prob", "pick", "final", "correct"]],
        use_container_width=True, hide_index=True,
    )
