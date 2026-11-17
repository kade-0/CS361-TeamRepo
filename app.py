"""Football analysis microservice. JSON only, no UI. See README.md for the API contract."""
import os
from flask import Flask, jsonify, request
from analysis import SORT_KEYS, analyze_match, chronological, leaders, live_dashboard, player_rows, sort_players
from event_analysis import MAJOR, build_timeline
from provider import ProviderError, get_provider

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

VALID_EVENT_TYPES = {"goal", "card", "substitution", "var", "other"}


def error(code, message, status):
    return jsonify(error={"code": code, "message": message}), status


def player_id_arg():
    """Returns (player_id or None, error response or None)."""
    raw = request.args.get("player_id")
    if raw is None:
        return None, None
    if not raw.isdigit():
        return None, error("bad_parameter", "player_id must be a whole number.", 400)
    return int(raw), None


def create_app(provider=None):
    app = Flask(__name__)
    prov = provider or get_provider()

    @app.after_request
    def cors(resp):   # lets browser-based programs on other origins call this service
        resp.headers["Access-Control-Allow-Origin"] = os.environ.get("CORS_ORIGIN", "*")
        return resp

    @app.errorhandler(ProviderError)
    def provider_error(e):
        return error(e.code, e.message, e.status)

    @app.errorhandler(404)
    def not_found(_):
        return error("not_found", "No such endpoint.", 404)

    @app.errorhandler(500)
    def server_error(_):
        return error("internal_error", "Unexpected server error.", 500)

    @app.get("/health")
    def health():
        return jsonify(status="ok", data_source=prov.name)

    @app.get("/v1/matches/live")
    def live():
        league = (request.args.get("league") or "").strip().lower()
        rows = []
        for f in prov.live_fixtures():
            if league and league not in f["league"]["name"].lower():
                continue
            rows.append({"id": f["fixture"]["id"], "league": f["league"]["name"], "home": f["teams"]["home"]["name"],
                         "away": f["teams"]["away"]["name"], "home_score": f["goals"]["home"] or 0,
                         "away_score": f["goals"]["away"] or 0, "minute": f["fixture"]["status"].get("elapsed") or 0,
                         "status": f["fixture"]["status"]["short"]})
        return jsonify(count=len(rows), matches=rows)

    @app.get("/v1/matches/<int:match_id>/analysis")
    def analysis(match_id):
        fixture = prov.fixture(match_id)
        if not fixture:
            return error("match_not_found", f"No match with id {match_id}.", 404)
        return jsonify(analyze_match(fixture, prov.statistics(match_id), prov.events(match_id)))

    @app.get("/v1/matches/<int:match_id>/dashboard")
    def dashboard(match_id):
        fixture = prov.fixture(match_id)
        if not fixture:
            return error("match_not_found", f"No match with id {match_id}.", 404)
        return jsonify(live_dashboard(fixture, prov.events(match_id)))

    @app.get("/v1/matches/<int:match_id>/events")
    def events(match_id):
        kind = (request.args.get("type") or "").lower()
        if kind and kind not in VALID_EVENT_TYPES:
            return error("bad_parameter", f"type must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}.", 400)
        pid, err = player_id_arg()
        if err:
            return err
        if not prov.fixture(match_id):
            return error("match_not_found", f"No match with id {match_id}.", 404)
        evs = chronological(prov.events(match_id))
        team = (request.args.get("team") or "").strip().lower()
        evs = [e for e in evs if (not kind or e["type"] == kind) and (not team or (e["team"] or "").lower() == team)
               and (pid is None or e["player_id"] == pid)]
        return jsonify(match_id=match_id, count=len(evs), events=evs)

    @app.get("/v1/matches/<int:match_id>/events/analysis")
    def events_analysis(match_id):
        kind = (request.args.get("type") or "").lower()
        if kind and kind not in VALID_EVENT_TYPES:
            return error("bad_parameter", f"type must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}.", 400)
        fixture = prov.fixture(match_id)
        if not fixture:
            return error("match_not_found", f"No match with id {match_id}.", 404)
        team = (request.args.get("team") or "").strip().lower()
        items = [e for e in build_timeline(fixture, prov.events(match_id))
                 if e["type"] in ({kind} if kind else set(MAJOR)) and (not team or (e["team"] or "").lower() == team)]
        return jsonify(match_id=match_id, count=len(items), events=items)

    @app.get("/v1/matches/<int:match_id>/events/<int:index>/analysis")
    def event_analysis(match_id, index):
        fixture = prov.fixture(match_id)
        if not fixture:
            return error("match_not_found", f"No match with id {match_id}.", 404)
        timeline = build_timeline(fixture, prov.events(match_id))
        if index >= len(timeline):
            return error("event_not_found", f"Match {match_id} has no event with index {index}.", 404)
        return jsonify(match_id=match_id, event=timeline[index])

    @app.get("/v1/matches/<int:match_id>/players")
    def players(match_id):
        sort = (request.args.get("sort") or "rating").lower()
        if sort not in SORT_KEYS:
            return error("bad_parameter", f"sort must be one of: {', '.join(sorted(SORT_KEYS))}.", 400)
        raw = request.args.get("limit", "10")
        if not raw.isdigit() or not 1 <= int(raw) <= 50:
            return error("bad_parameter", "limit must be a whole number from 1 to 50.", 400)
        pid, err = player_id_arg()
        if err:
            return err
        if not prov.fixture(match_id):
            return error("match_not_found", f"No match with id {match_id}.", 404)
        rows = player_rows(prov.players(match_id))
        if pid is not None:
            rows = [r for r in rows if r["player_id"] == pid]
        team = (request.args.get("team") or "").strip().lower()
        if team:
            rows = [r for r in rows if (r["team"] or "").lower() == team]
        return jsonify(match_id=match_id, count=len(rows), sorted_by=sort, leaders=leaders(rows),
                       players=sort_players(rows, sort)[:int(raw)])

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5001")), debug=False,
                     use_reloader=False, threaded=os.environ.get("THREADED", "1") == "1")