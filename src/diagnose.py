import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

url = "https://stats.nba.com/stats/leaguegamelog"
params = {
    "Counter": 1000,
    "Direction": "DESC",
    "LeagueID": "00",
    "PlayerOrTeam": "T",
    "Season": "2025-26",
    "SeasonType": "Regular Season",
    "Sorter": "DATE",
}

try:
    r = requests.get(url, headers=headers, params=params, timeout=30)
    print("Status code:", r.status_code)
    print("First 400 characters of the response:")
    print(r.text[:400])
except Exception as e:
    print("Request failed:", type(e).__name__, e)