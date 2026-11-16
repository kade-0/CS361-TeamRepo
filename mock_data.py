"""Mock data in API-Football v3 response format. Player names are fictional."""

def _fx(fid, league, lid, status, long_, elapsed, home, hid, away, aid, hg, ag):
    return {"fixture": {"id": fid, "status": {"long": long_, "short": status, "elapsed": elapsed}},
            "league": {"id": lid, "name": league},
            "teams": {"home": {"id": hid, "name": home}, "away": {"id": aid, "name": away}},
            "goals": {"home": hg, "away": ag}}

FIXTURES = {
    1001: _fx(1001, "Premier League", 39, "2H", "Second Half", 67, "Tottenham", 47, "Coventry City", 1500, 2, 1),
    1002: _fx(1002, "Major League Soccer", 253, "1H", "First Half", 38, "Portland", 1600, "Seattle", 1601, 0, 0),
    1003: _fx(1003, "Serie A", 135, "FT", "Match Finished", 90, "Inter Milan", 505, "A.C. Milan", 489, 2, 0),
}

def _stats(team, tid, rows):
    return {"team": {"id": tid, "name": team}, "statistics": [{"type": t, "value": v} for t, v in rows]}

STATISTICS = {
    1001: [
        _stats("Tottenham", 47, [("Shots on Goal", 6), ("Shots off Goal", 4), ("Total Shots", 14), ("Blocked Shots", 4),
                                 ("Fouls", 9), ("Corner Kicks", 7), ("Yellow Cards", 1), ("Red Cards", None),
                                 ("Goalkeeper Saves", 2), ("Ball Possession", "58%"), ("Total passes", 412),
                                 ("Passes accurate", 351), ("Passes %", "85%"), ("expected_goals", "2.31")]),
        _stats("Coventry City", 1500, [("Shots on Goal", 3), ("Shots off Goal", 2), ("Total Shots", 7), ("Blocked Shots", 2),
                                       ("Fouls", 12), ("Corner Kicks", 2), ("Yellow Cards", 3), ("Red Cards", None),
                                       ("Goalkeeper Saves", 4), ("Ball Possession", "42%"), ("Total passes", 301),
                                       ("Passes accurate", 226), ("Passes %", "75%"), ("expected_goals", "0.94")]),
    ],
    1002: [
        _stats("Portland", 1600, [("Shots on Goal", 1), ("Total Shots", 3), ("Fouls", 4), ("Corner Kicks", 1),
                                  ("Ball Possession", "49%"), ("Total passes", 150), ("Passes accurate", 120)]),
        _stats("Seattle", 1601, [("Shots on Goal", 2), ("Total Shots", 4), ("Fouls", 5), ("Corner Kicks", 2),
                                 ("Ball Possession", "51%"), ("Total passes", 160), ("Passes accurate", 130)]),
    ],
}

def _ev(el, extra, team, tid, player, typ, detail, assist=None):
    return {"time": {"elapsed": el, "extra": extra}, "team": {"id": tid, "name": team},
            "player": {"id": None, "name": player}, "assist": {"id": None, "name": assist},
            "type": typ, "detail": detail, "comments": None}

EVENTS = {
    1001: [
        _ev(14, None, "Tottenham", 47, "M. Duarte", "Goal", "Normal Goal", "L. Brandt"),
        _ev(31, None, "Coventry City", 1500, "K. Osei", "Card", "Yellow Card"),
        _ev(49, None, "Coventry City", 1500, "R. Vance", "Goal", "Normal Goal", "K. Osei"),
        _ev(58, None, "Tottenham", 47, "S. Halvorsen", "Goal", "Penalty"),
        _ev(60, None, "Tottenham", 47, "L. Brandt", "subst", "Substitution 1", "T. Ivanov"),
        _ev(64, None, "Coventry City", 1500, "D. Mills", "Card", "Red Card"),
    ],
    1002: [_ev(22, None, "Seattle", 1601, "A. Ruiz", "Card", "Yellow Card")],
}
