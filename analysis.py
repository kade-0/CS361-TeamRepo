"""Pure analysis functions. Input is API-Football v3 format; no network, no Flask."""

STAT_KEYS = {"Ball Possession": "possession", "Total Shots": "shots_total", "Shots on Goal": "shots_on_target",
             "Shots off Goal": "shots_off_target", "Blocked Shots": "shots_blocked", "Total passes": "passes_total",
             "Passes accurate": "passes_accurate", "Passes %": "pass_accuracy", "Fouls": "fouls",
             "Corner Kicks": "corners", "Yellow Cards": "yellow_cards", "Red Cards": "red_cards",
             "Goalkeeper Saves": "saves", "expected_goals": "xg"}
# How "who is on top" is scored. Each metric's share between the teams is weighted.
DOMINANCE_WEIGHTS = [("possession", 0.30), ("shots_on_target", 0.35), ("shots_total", 0.20), ("corners", 0.15)]
EVENT_TYPES = {"Goal": "goal", "Card": "card", "subst": "substitution", "Var": "var"}


def to_number(value, default=0):
    """API-Football sends numbers as ints, strings like '58%', '2.31', or null."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().rstrip("%")
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return default


def team_stats(block):
    out = {k: 0 for k in STAT_KEYS.values()}
    out["xg"] = None
    for item in block.get("statistics", []):
        key = STAT_KEYS.get(item.get("type"))
        if key:
            out[key] = to_number(item.get("value"), None if key == "xg" else 0)
    if not out["pass_accuracy"] and out["passes_total"]:
        out["pass_accuracy"] = round(100 * out["passes_accurate"] / out["passes_total"], 1)
    out["shot_accuracy"] = round(100 * out["shots_on_target"] / out["shots_total"], 1) if out["shots_total"] else 0.0
    out["name"] = (block.get("team") or {}).get("name")
    return out


def _pick(blocks, team, fallback_index):
    for b in blocks:
        t = b.get("team") or {}
        if t.get("id") is not None and t.get("id") == team.get("id"):
            return b
    for b in blocks:
        if (b.get("team") or {}).get("name") == team.get("name"):
            return b
    return blocks[fallback_index] if len(blocks) > fallback_index else None


def _share(a, b):
    return 50.0 if (a + b) == 0 else 100.0 * a / (a + b)


def dominance(home, away):
    h = sum(w * _share(home[k], away[k]) for k, w in DOMINANCE_WEIGHTS)
    h = round(h, 1)
    verdict = "home" if h >= 60 else "away" if h <= 40 else "balanced"
    return {"home_share": h, "away_share": round(100 - h, 1), "verdict": verdict,
            "method": "Weighted share of possession (30%), shots on target (35%), total shots (20%), corners (15%)."}


def normalize_event(e):
    t = e.get("time") or {}
    el, extra = t.get("elapsed") or 0, t.get("extra") or 0
    return {"minute": el, "extra": extra, "clock": f"{el}'+{extra}'" if extra else f"{el}'",
            "team": (e.get("team") or {}).get("name"), "team_id": (e.get("team") or {}).get("id"),
            "player": (e.get("player") or {}).get("name"), "player_id": (e.get("player") or {}).get("id"),
            "assist": (e.get("assist") or {}).get("name"), "assist_id": (e.get("assist") or {}).get("id"), "type": EVENT_TYPES.get(e.get("type"), "other"),
            "detail": e.get("detail"), "comments": e.get("comments")}


def chronological(raw_events):
    """Normalized events in match order, each with a stable 0-based `index`."""
    evs = sorted((normalize_event(e) for e in raw_events), key=lambda e: (e["minute"], e["extra"]))
    for i, e in enumerate(evs):
        e["index"] = i
    return evs


def is_key_moment(ev):
    d = (ev["detail"] or "").lower()
    return ev["type"] in ("goal", "var") or (ev["type"] == "card" and ("red" in d or "second yellow" in d))


def _summary(match, stats_ok, dom, home, away):
    h, a = match["home_score"], match["away_score"]
    who = match["home"] if h > a else match["away"] if a > h else None
    if match["status"] in ("FT", "AET", "PEN"):
        line = f"Full time: {match['home']} {h}-{a} {match['away']}."
    elif who:
        line = f"{who} lead {max(h, a)}-{min(h, a)} after {match['minute']}'."
    else:
        line = f"{match['home']} and {match['away']} are level at {h}-{a} after {match['minute']}'."
    if not stats_ok:
        return line + " Detailed statistics are not available yet."
    if dom["verdict"] == "balanced":
        return line + " The match is evenly balanced on the statistics."
    top, t = (match["home"], home) if dom["verdict"] == "home" else (match["away"], away)
    return (line + f" {top} are on top with {t['possession']}% possession and "
            f"{t['shots_on_target']} shots on target out of {t['shots_total']}.")


def analyze_match(fixture, stat_blocks, events):
    teams = fixture["teams"]
    match = {"id": fixture["fixture"]["id"], "league": fixture["league"]["name"],
             "status": fixture["fixture"]["status"]["short"], "minute": fixture["fixture"]["status"].get("elapsed") or 0,
             "home": teams["home"]["name"], "away": teams["away"]["name"],
             "home_score": fixture["goals"]["home"] or 0, "away_score": fixture["goals"]["away"] or 0}
    hb, ab = _pick(stat_blocks, teams["home"], 0), _pick(stat_blocks, teams["away"], 1)
    ok = bool(hb and ab)
    home, away = (team_stats(hb), team_stats(ab)) if ok else (None, None)
    dom = dominance(home, away) if ok else None
    evs = chronological(events)
    return {"match": match, "statistics_available": ok, "teams": {"home": home, "away": away} if ok else None,
            "dominance": dom, "key_moments": [e for e in evs if is_key_moment(e)],
            "summary": _summary(match, ok, dom, home, away)}


# ---------------------------------------------------------------- player analysis
def _rate(part, whole):
    return round(100 * part / whole, 1) if whole else 0.0


def player_row(team_name, entry, team_id=None):
    st = (entry.get("statistics") or [{}])[0]
    g, sh, go, pa = (st.get(k) or {} for k in ("games", "shots", "goals", "passes"))
    du, dr, ta, fo, ca = (st.get(k) or {} for k in ("duels", "dribbles", "tackles", "fouls", "cards"))
    n = lambda v: to_number(v, 0)
    row = {"player_id": (entry.get("player") or {}).get("id"), "name": (entry.get("player") or {}).get("name"),
           "team_id": team_id, "team": team_name, "position": g.get("position"),
           "minutes": n(g.get("minutes")), "rating": to_number(g.get("rating"), None),
           "goals": n(go.get("total")), "assists": n(go.get("assists")),
           "shots_total": n(sh.get("total")), "shots_on_target": n(sh.get("on")),
           "key_passes": n(pa.get("key")), "passes_total": n(pa.get("total")),
           "duels_total": n(du.get("total")), "duels_won": n(du.get("won")),
           "dribbles_attempted": n(dr.get("attempts")), "dribbles_success": n(dr.get("success")),
           "tackles": n(ta.get("total")), "interceptions": n(ta.get("interceptions")),
           "fouls_committed": n(fo.get("committed")), "fouls_drawn": n(fo.get("drawn")),
           "yellow_cards": n(ca.get("yellow")), "red_cards": n(ca.get("red"))}
    row["shot_accuracy"] = _rate(row["shots_on_target"], row["shots_total"])
    row["duel_win_rate"] = _rate(row["duels_won"], row["duels_total"])
    row["dribble_success_rate"] = _rate(row["dribbles_success"], row["dribbles_attempted"])
    return row


def player_rows(blocks):
    """Flatten the provider's per-team player lists. Unused substitutes (no minutes) are dropped."""
    rows = []
    for b in blocks:
        for entry in b.get("players", []):
            row = player_row((b.get("team") or {}).get("name"), entry, (b.get("team") or {}).get("id"))
            if row["minutes"] > 0:
                rows.append(row)
    return rows


def _leader(rows, key, minimum=1, label=None):
    pool = [r for r in rows if (r[key] or 0) >= minimum]
    if not pool:
        return None
    best = max(pool, key=lambda r: r[key])
    return {"player_id": best["player_id"], "player": best["name"], "team": best["team"], "value": best[key]}


def leaders(rows):
    """Standout player in each area. Rates need a minimum sample so one dribble can't win."""
    out = {"rating": _leader([r for r in rows if r["rating"] is not None], "rating"),
           "goals": _leader(rows, "goals"), "assists": _leader(rows, "assists"),
           "key_passes": _leader(rows, "key_passes"), "shots": _leader(rows, "shots_total"),
           "tackles": _leader(rows, "tackles")}
    out["duel_win_rate"] = _leader([r for r in rows if r["duels_total"] >= 5], "duel_win_rate")
    out["dribble_success_rate"] = _leader([r for r in rows if r["dribbles_attempted"] >= 3], "dribble_success_rate")
    return out


SORT_KEYS = {"rating": "rating", "goals": "goals", "key_passes": "key_passes", "shots": "shots_total"}


def sort_players(rows, sort="rating"):
    key = SORT_KEYS[sort]
    return sorted(rows, key=lambda r: (r[key] is None, -(r[key] or 0), r["name"] or ""))