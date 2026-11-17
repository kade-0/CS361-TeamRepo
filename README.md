# CS361-TeamRepo

A collection of the Microservices for each program, check the branches out for details!

## Team Effort

Kade - Organizing and management of the repository and project, worked on `accounts` and `analysis`

Sam - Worked on `analysis` and `reports`

Garrett - Worked on `reports` and `banking`

Deon - Worked on `banking`

<img width="1075" height="591" alt="image" src="https://github.com/user-attachments/assets/a0e4d3ac-e71d-424f-8d2e-9450ce30c302" />

Analysis Serivce: 

A backend-only service (no user interface) that turns raw football (soccer) data from API-Football (v3) into analysis other programs can use. Any program that can send an HTTP GET request and read JSON can call it.

It provides three kinds of analysis:

Match analysis: team statistics (possession, shots, passing, xG), a "who is on top" score, key moments, and a plain-English summary.
Player analysis: per-player statistics, derived rates (shot accuracy, duel win rate), and the standout player in each area.
Event analysis: for each goal, card, and VAR decision, the score before and after, the match phase, what the event changed, and running totals (braces, hat-tricks, margin).

It describes the situation around events. It does not claim to know why a player acted, and it cannot analyze individual missed shots, passes, or fouls because API-Football does not list them as events, which is why this is kind of limited in this sense.

Protocol: HTTP GET only. No request body, no API key, no login. The caller never needs an API-Football key; only the service holds it.
Base URL: http://127.0.0.1:5001 (change the port with the PORT environment variable).
Ids: a match id comes from GET /v1/matches/live. An event index comes from the index field on events returned by /events, /events/analysis, or key_moments in /analysis.

How to request data:

GET /health (Path Parameters: NONE)	-- Check the service is running and which data source it uses
GET /v1/matches/live	(Path Parameters: NONE)	(Optional Path Parameters: league (text, matches part of the league name)) --	List matches in progress
GET /v1/matches/{id}/analysis	(Path Parameters: id (whole number))	(Optional Path Parameters: none) --	Match-level analysis
GET /v1/matches/{id}/players	(Path Parameters: id)	(Optional Path Parameters: team (exact team name), player_id (whole number), sort (rating, goals, key_passes, shots; default rating), limit (1 to 50; default 10)) -- Player analysis
GET /v1/matches/{id}/events	(Path Parameters: id) (Optional Path Parameters: type (goal, card, substitution, var, other), team (exact name), player_id) --	Raw events in match order
GET /v1/matches/{id}/events/analysis	(Path Parameters: id) 	(Optional Path Parameters: type (same values; default is goals, cards and VAR), team) -- 	Analysis of every matching event
GET /v1/matches/{id}/events/{index}/analysis	(Path Parameters: id, index (whole number from 0)) 	(Optional Path Parameters: none) -- Analysis of one event

Example Request: import requests

BASE = "http://127.0.0.1:5001"

live = requests.get(f"{BASE}/v1/matches/live", timeout=5)
match_id = live.json()["matches"][0]["id"]

resp = requests.get(f"{BASE}/v1/matches/{match_id}/players",
                    params={"sort": "rating", "limit": 3}, timeout=5)

How to receive data:

Endpoint	Body
/health
--{status, data_source}
--where data_source is "mock" or "api-football"
/v1/matches/live	
--{count, matches:[{id, league, home, away, home_score, away_score, minute, status}]}.
--status is API-Football's short code, e.g. 1H, HT, 2H.
/v1/matches/{id}/analysis
--{match, statistics_available, teams, dominance, key_moments, summary}. match = {id, league, status, minute, home, away, home_score, away_score}. teams = {home, away} or null when statistics are unavailable; each has name, possession, shots_total, shots_on_target, shots_off_target, shots_blocked, shot_accuracy, passes_total, passes_accurate, pass_accuracy, fouls, corners, yellow_cards, red_cards, saves, xg (xg may be null). dominance = {home_share, away_share, verdict, method} (verdict is home, away or balanced) or null. 
--key_moments is a list of events.
/v1/matches/{id}/players	
--{match_id, count, sorted_by, leaders, players}. 
--Each player: player_id, name, team_id, team, position, minutes, rating, goals, assists, shots_total, shots_on_target, shot_accuracy, key_passes, passes_total, duels_total, duels_won, duel_win_rate, dribbles_attempted, dribbles_success, dribble_success_rate, tackles, interceptions, fouls_committed, fouls_drawn, yellow_cards, red_cards. leaders has rating, goals, assists, key_passes, shots, tackles, duel_win_rate, dribble_success_rate, each {player_id, player, team, value} or null if nobody qualifies.
/v1/matches/{id}/events	
--{match_id, count, events:[{index, minute, extra, clock, team, team_id, player, player_id, assist, assist_id, type, detail, comments}]}. 
--type is goal, card, substitution, var or other.
/v1/matches/{id}/events/analysis	
--{match_id, count, events} 
--where each event has all the fields above plus side, phase, score_before, score_after, game_state, headline, insights, and type-specific fields below.
/v1/matches/{id}/events/{index}/analysis	
--{match_id, event}
--with the same event fields.


Example Request: 
import requests

resp = requests.get("http://127.0.0.1:5001/v1/matches/1528990/analysis", timeout=5)

if resp.status_code == 200:
    data = resp.json()                         # parse the JSON body into a dict
    print(data["summary"])                     # e.g. "Germany lead 1-0 after 45'. ..."
    home = data["teams"]["home"] if data["statistics_available"] else None
    if home:
        print(home["name"], home["possession"], "% possession")
else:
    error = resp.json()["error"]               # errors are JSON too
    print(resp.status_code, error["code"], error["message"])

<img width="468" height="437" alt="image" src="https://github.com/user-attachments/assets/2d4d3823-141c-4ba0-bec6-d1663b674652" />
