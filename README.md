# Football Analysis Microservice

Backend-only JSON service that pulls live match data from [API-Football](https://www.api-football.com/) (v3) and returns analysis: team statistics, a "who is on top" score, key moments, and a plain-English summary. Any program that can send an HTTP GET can use it.

## Run
```
pip install -r requirements.txt
cp .env.example .env        # then edit .env
python app.py               # http://127.0.0.1:5001
python -m pytest            # 27 tests, no network or key needed
```
**API key:** put it in `.env` as `API_FOOTBALL_KEY=...` (never commit `.env`). While the key is missing or still the placeholder `YOUR_API_FOOTBALL_KEY_HERE`, the service serves built-in **mock data** in API-Football's format. `GET /health` shows which source is active (`"mock"` or `"api-football"`). Set `USE_MOCK=1` to force mock data.

## Endpoints (all GET, all JSON, no authentication)
| Endpoint | Parameters | Returns |
|---|---|---|
| `/health` | none | `{status, data_source}` |
| `/v1/matches/live` | `league` (optional, name substring) | `{count, matches:[{id, league, home, away, home_score, away_score, minute, status}]}` |
| `/v1/matches/{id}/analysis` | `id` in path (required) | `{match, statistics_available, teams:{home,away}, dominance, key_moments[], summary}` |
| `/v1/matches/{id}/players` | `id` in path; `team` (exact name), `player_id` (integer), `sort` (rating/goals/key_passes/shots, default rating), `limit` (1-50, default 10) optional | `{match_id, count, sorted_by, leaders, players:[...]}` |
| `/v1/matches/{id}/events` | `id` in path; `type` (goal/card/substitution/var/other), `team` (exact name), `player_id` (integer) optional | `{match_id, count, events:[{minute, extra, clock, team, team_id, player, player_id, assist, assist_id, type, detail}]}` |

`teams.home/away` contain: `possession, shots_total, shots_on_target, shots_off_target, shots_blocked, shot_accuracy, passes_total, passes_accurate, pass_accuracy, fouls, corners, yellow_cards, red_cards, saves, xg` (`xg` is null when the provider has none).
`players[]` each have: `player_id, name, team_id, team, position, minutes, rating, goals, assists, shots_total, shots_on_target, shot_accuracy, key_passes, passes_total, duels_total, duels_won, duel_win_rate, dribbles_attempted, dribbles_success, dribble_success_rate, tackles, interceptions, fouls_committed, fouls_drawn, yellow_cards, red_cards`. Players who did not play are omitted; `rating` is null if unrated. `leaders` names the standout player for rating, goals, assists, key_passes, shots, tackles, duel_win_rate (min 5 duels) and dribble_success_rate (min 3 dribbles); a leader is null if nobody qualifies.
`dominance`: `{home_share, away_share, verdict: home|away|balanced, method}`.

## Errors
Always JSON: `{"error": {"code": "...", "message": "..."}}`

| Status | code | Meaning |
|---|---|---|
| 400 | `bad_parameter` | invalid query parameter |
| 404 | `match_not_found` / `not_found` | unknown match id / endpoint |
| 429 | `rate_limited` | API-Football quota reached |
| 502 | `upstream_error`, `upstream_unreachable`, `upstream_auth` | provider problem or rejected key |

## Example
```
curl http://127.0.0.1:5001/v1/matches/live
curl http://127.0.0.1:5001/v1/matches/1001/analysis
curl "http://127.0.0.1:5001/v1/matches/1001/events?type=goal"
curl "http://127.0.0.1:5001/v1/matches/1001/players?sort=key_passes&limit=3"
python demo_client.py     # example program calling the service
```
```python
import requests
r = requests.get("http://127.0.0.1:5001/v1/matches/1001/analysis", timeout=5)
if r.ok: print(r.json()["summary"])
```

## Notes
- Upstream responses are cached for `CACHE_TTL` seconds (default 10) to protect your API quota. One `/analysis` call uses up to 3 upstream requests; `/players` uses 1 (plus 1 to confirm the match exists).
- Mock player names are fictional. On a shared school server, run with `THREADED=0` if you hit "can't start new thread".
- Code layout: `app.py` routes, `analysis.py` pure analysis, `provider.py` API-Football client + mock, `mock_data.py`, `tests/`.

## Joining events and players
API-Football spells names differently across endpoints (`Joshua Kimmich` in events, `J. Kimmich` in players). Always join on `player_id` (and `team_id`), never on name. An id is `null` if the provider doesn't supply one. `leaders` entries also carry `player_id`.