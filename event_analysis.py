"""Context analysis for individual match events (goals, cards, VAR). Pure functions, no network.
It describes the SITUATION around an event (score, timing, what it changed). It does not
claim to know why a player acted."""
from analysis import chronological

MAJOR = ("goal", "card", "var")


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def phase(minute, extra):
    if minute > 90: return "extra time"
    if minute == 90 and extra: return "second-half stoppage time"
    if minute == 45 and extra: return "first-half stoppage time"
    if minute <= 15: return "opening 15 minutes"
    if minute <= 40: return "first half"
    if minute <= 45: return "end of first half"
    if minute <= 55: return "start of second half"
    if minute <= 75: return "second half"
    return "closing stages"


def _when(e):
    return f"in stoppage time ({e['clock']})" if e["extra"] else f"in the {ordinal(e['minute'])} minute"


def _other(side):
    return "away" if side == "home" else "home"


def _side(e, fx):
    h, a = fx["teams"]["home"], fx["teams"]["away"]
    if e["team_id"] is not None and e["team_id"] in (h.get("id"), a.get("id")):
        return "home" if e["team_id"] == h.get("id") else "away"
    return "home" if e["team"] == h["name"] else "away" if e["team"] == a["name"] else None


def _is_own_goal(e):
    return "own goal" in (e["detail"] or "").lower()


def _is_scoring(e):
    return (e["type"] == "goal" and "missed" not in (e["detail"] or "").lower()
            and "shootout" not in (e["comments"] or "").lower())


def _credit(e, side, mode):
    return _other(side) if _is_own_goal(e) and mode == "opponent" else side


def _tally(evs, fx, mode):
    t = {"home": 0, "away": 0}
    for e in evs:
        s = _side(e, fx)
        if s and _is_scoring(e):
            t[_credit(e, s, mode)] += 1
    return (t["home"], t["away"])


def own_goal_mode(evs, fx):
    """Providers differ on which team an own goal is listed under. Pick the reading whose
    total matches the official score; otherwise assume it is listed under the player's team."""
    if not any(_is_own_goal(e) and _is_scoring(e) for e in evs):
        return "opponent", None
    target = (fx["goals"]["home"] or 0, fx["goals"]["away"] or 0)
    for mode in ("opponent", "team"):
        if _tally(evs, fx, mode) == target:
            return mode, None
    return "opponent", "Goal events do not add up to the official score, so own-goal credit is assumed."


def significance(before, scorer):
    d = before[scorer] - before[_other(scorer)]
    if before["home"] + before["away"] == 0: return "opening goal"
    if d == -1: return "equalizer"
    if d == 0: return "go-ahead goal"
    if d >= 1: return "extends lead"
    return "reduces deficit"


def game_state(score, side):
    if side is None: return None
    m = score[side] - score[_other(side)]
    return {"for_team": "leading" if m > 0 else "trailing" if m < 0 else "level", "margin": abs(m)}


def _state_text(score, side, names):
    gs = game_state(score, side)
    if gs is None: return None
    if gs["for_team"] == "level": return f"the score was level at {score['home']}-{score['away']}"
    return f"{names[side]} were {gs['for_team']} {score[side]}-{score[_other(side)]}"


def build_timeline(fx, raw_events):
    evs = chronological(raw_events)
    mode, note = own_goal_mode(evs, fx)
    names = {"home": fx["teams"]["home"]["name"], "away": fx["teams"]["away"]["name"]}
    elapsed = fx["fixture"]["status"].get("elapsed") or (evs[-1]["minute"] if evs else 0)
    scorer_at = {e["index"]: _credit(e, _side(e, fx), mode) for e in evs if _side(e, fx) and _is_scoring(e)}
    score = {"home": 0, "away": 0}
    reds, yellows, player_cards = {"home": 0, "away": 0}, {"home": 0, "away": 0}, {}
    last_goal_min, lead = None, (None, 0)          # lead = (side currently ahead, minute that began)
    for e in evs:
        side, before = _side(e, fx), dict(score)
        e["side"], e["phase"], e["score_before"] = side, phase(e["minute"], e["extra"]), before
        e["game_state"] = game_state(before, side)
        insights, state = [], (_state_text(before, side, names) if side else None)
        who = f"{e['player']} ({e['team']})" if e["player"] else e["team"]

        if e["type"] == "goal" and e["index"] in scorer_at:
            s = scorer_at[e["index"]]; T = names[s]
            sig = significance(before, s)
            trailing_for = e["minute"] - lead[1] if sig == "equalizer" and lead[0] == _other(s) else None
            score[s] += 1
            after_txt = f"{score['home']}-{score['away']}"
            head = {"opening goal": f"{T} score first {_when(e)}.",
                    "equalizer": f"{T} equalize {_when(e)}, making it {after_txt}"
                                 + (f", ending {trailing_for} minutes of trailing." if trailing_for else "."),
                    "go-ahead goal": f"{T} take the lead {_when(e)}, {after_txt}.",
                    "extends lead": f"{T} extend their lead to {after_txt} {_when(e)}.",
                    "reduces deficit": f"{T} pull a goal back {_when(e)}, making it {after_txt}."}[sig]
            insights.append(head)
            e["significance"], e["scoring_team"] = sig, T
            if _is_own_goal(e): insights.append(f"Own goal by {e['player']}; the goal is credited to {T}.")
            elif "penalty" in (e["detail"] or "").lower(): insights.append("Scored from the penalty spot.")
            elif e["assist"]: insights.append(f"Assisted by {e['assist']}.")
            if last_goal_min is not None:
                gap = e["minute"] - last_goal_min
                e["minutes_since_previous_goal"] = gap
                if gap <= 5: insights.append(f"Comes only {gap} minute(s) after the previous goal.")
            if e["phase"] in ("end of first half", "first-half stoppage time"): insights.append("Scored just before half-time.")
            if e["phase"] == "start of second half": insights.append("Scored shortly after half-time.")
            if e["phase"] in ("closing stages", "second-half stoppage time") and sig in ("equalizer", "go-ahead goal"):
                insights.append("A late goal that changes who is ahead.")
            last_goal_min = e["minute"]
            leader = "home" if score["home"] > score["away"] else "away" if score["away"] > score["home"] else None
            if leader != lead[0]: lead = (leader, e["minute"])
        elif e["type"] == "goal":                                   # missed penalty or similar
            e["significance"] = "penalty missed"
            insights.append(f"{who} misses a penalty {_when(e)}.")
            if side:
                would = {"opening goal": "an opening goal", "equalizer": "an equalizer", "go-ahead goal": "a go-ahead goal",
                         "extends lead": "a goal extending the lead", "reduces deficit": "a goal reducing the deficit"}
                insights.append(f"Scoring would have been {would[significance(before, side)]}.")
        elif e["type"] == "card":
            d = (e["detail"] or "").lower()
            key = e["player_id"] if e["player_id"] is not None else e["player"]
            e["player_cards_before"] = player_cards.get(key, 0)
            player_cards[key] = e["player_cards_before"] + 1
            sent_off = "red" in d or "second yellow" in d
            if side and not sent_off: yellows[side] += 1
            if side and sent_off: reds[side] += 1
            if side:
                e["team_cards"] = {"yellow": yellows[side], "red": reds[side]}
            if sent_off and side:
                men = 11 - reds[side]
                e["men_on_pitch"] = men
                insights.append(f"{who} is sent off {_when(e)}, leaving {names[side]} with {men} players.")
                if "second yellow" in d: insights.append("This was a second booking.")
                if e["minute"] <= 90:
                    e["minutes_remaining"] = max(0, 90 - e["minute"])
                    insights.append(f"About {e['minutes_remaining']} minutes of normal time remained.")
                since = {"home": 0, "away": 0}
                for k, s in scorer_at.items():
                    if k > e["index"]: since[s] += 1
                e["after_effect"] = {"minutes_played_since": max(0, elapsed - e["minute"]),
                                     "goals_since": {"home": since["home"], "away": since["away"]}}
                insights.append("Since then: " + (f"{names['home']} {since['home']}, {names['away']} {since['away']} (goals scored)."
                                if since["home"] or since["away"] else "neither side has scored."))
            else:
                insights.append(f"{who} is booked {_when(e)}.")
                if side and yellows[side] >= 3: insights.append(f"{names[side]}'s {ordinal(yellows[side])} yellow card of the match.")
        elif e["type"] == "var":
            insights.append(f"VAR decision {_when(e)}: {e['detail']}.")
        elif e["type"] == "substitution":
            insights.append(f"Substitution for {e['team']} {_when(e)}.")
        else:
            insights.append(f"{e['detail'] or 'Event'} {_when(e)}.")
        if state and e["type"] != "goal": insights.append(f"At the time, {state}.")
        e["score_after"] = dict(score)
        e["headline"], e["insights"] = insights[0], insights[1:]
    if note and evs:
        evs[0]["note"] = note
    return evs