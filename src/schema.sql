CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    abbreviation TEXT,
    name TEXT
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    name TEXT
);

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    game_date TEXT NOT NULL,
    season INTEGER,
    season_type TEXT,
    home_team_id TEXT,
    away_team_id TEXT,
    home_score INTEGER,
    away_score INTEGER
);

CREATE TABLE IF NOT EXISTS team_game_stats (
    game_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    home_away TEXT,
    pts INTEGER, opp_pts INTEGER, win INTEGER,
    fgm INTEGER, fga INTEGER,
    fg3m INTEGER, fg3a INTEGER,
    ftm INTEGER, fta INTEGER,
    oreb INTEGER, dreb INTEGER, reb INTEGER,
    ast INTEGER, stl INTEGER, blk INTEGER,
    tov INTEGER, pf INTEGER,
    pts_in_paint INTEGER, fast_break_pts INTEGER,
    PRIMARY KEY (game_id, team_id)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    game_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    team_id TEXT,
    starter INTEGER,
    minutes INTEGER,
    pts INTEGER,
    fgm INTEGER, fga INTEGER,
    fg3m INTEGER, fg3a INTEGER,
    ftm INTEGER, fta INTEGER,
    reb INTEGER, ast INTEGER, tov INTEGER,
    stl INTEGER, blk INTEGER,
    oreb INTEGER, dreb INTEGER,
    pf INTEGER, plus_minus INTEGER,
    PRIMARY KEY (game_id, player_id)
);