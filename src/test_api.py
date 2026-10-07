from nba_api.stats.endpoints import leaguegamefinder

games = leaguegamefinder.LeagueGameFinder(
    player_or_team_abbreviation="T",
    season_nullable="2025-2026",
    season_type_nullable="Regular Season",
    timeout=60,
).get_data_frames()[0]

print(len(games),"rows")
print(games[["GAME_DATE", "TEAM_ABBREVIATION", "MATCHUP","WL","PTS"]].head())