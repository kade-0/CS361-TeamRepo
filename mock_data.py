"""Mock data in API-Football v3 response format. Player names are fictional."""

def _fx(fid, league, lid, status, long_, elapsed, home, hid, away, aid, hg, ag):
    return {"fixture": {"id": fid, "status": {"long": long_, "short": status, "elapsed": elapsed}},
            "league": {"id": lid, "name": league},
            "teams": {"home": {"id": hid, "name": home}, "away": {"id": aid, "name": away}},
            "goals": {"home": hg, "away": ag}}

FIXTURES = {
    1001: _fx(1001, "Premier League", 39, "2H", "Second Half", 67, "Tottenham", 47, "Coventry City", 1500, 2, 1),
    1002: _fx(1002, "Major League Soccer", 253, "1H", "First Half", 38, "Portland", 1600, "Seattle", 1601, 0, 0),
    1004: _fx(1004, "Premier League", 39, "FT", "Match Finished", 90, "Harbor FC", 700, "Ridgeline SC", 701, 2, 2),
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

PLAYER_IDS = {"M. Duarte": 101, "S. Halvorsen": 102, "L. Brandt": 103, "A. Weiss": 104, "T. Ivanov": 105,
              "B. Reserve": 106, "J. Marsh": 401, "C. Dunn": 402, "T. Boyd": 403, "N. Park": 404, "R. Aziz": 405, "Z. Okoro": 406, "R. Vance": 201, "K. Osei": 202, "D. Mills": 203, "P. Njoku": 204, "A. Ruiz": 301}


def _ev(el, extra, team, tid, player, typ, detail, assist=None):
    return {"time": {"elapsed": el, "extra": extra}, "team": {"id": tid, "name": team},
            "player": {"id": PLAYER_IDS.get(player), "name": player}, "assist": {"id": PLAYER_IDS.get(assist), "name": assist},
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


def _pl(tid, tname, rows):
    out = []
    for (name, pos, mins, rating, goals, assists, shots, on, key, ptotal, duels, won, drib, dsucc, tack, inter, fc, fd, yc, rc) in rows:
        out.append({"player": {"id": PLAYER_IDS.get(name), "name": name}, "statistics": [{
            "games": {"minutes": mins, "position": pos, "rating": rating},
            "shots": {"total": shots, "on": on}, "goals": {"total": goals, "assists": assists},
            "passes": {"total": ptotal, "key": key}, "duels": {"total": duels, "won": won},
            "dribbles": {"attempts": drib, "success": dsucc}, "tackles": {"total": tack, "interceptions": inter},
            "fouls": {"committed": fc, "drawn": fd}, "cards": {"yellow": yc, "red": rc}}]})
    return {"team": {"id": tid, "name": tname}, "players": out}

# name, pos, min, rating, goals, assists, shots, on, key passes, passes, duels, won, dribbles, success, tackles, interceptions, fouls, drawn, yellow, red
PLAYERS = {
    1001: [
        _pl(47, "Tottenham", [("M. Duarte", "F", 67, "8.1", 1, 0, 4, 3, 2, 31, 14, 9, 6, 4, 1, 0, 1, 3, 0, 0),
                              ("S. Halvorsen", "M", 67, "7.6", 1, 0, 3, 2, 3, 48, 12, 7, 2, 1, 2, 1, 2, 2, 0, 0),
                              ("L. Brandt", "M", 60, "7.2", 0, 1, 1, 1, 4, 55, 9, 5, 3, 2, 1, 2, 0, 1, 0, 0),
                              ("A. Weiss", "D", 67, "6.9", 0, 0, 0, 0, 0, 62, 10, 7, 0, 0, 4, 3, 2, 0, 1, 0),
                              ("T. Ivanov", "M", 7, None, 0, 0, 0, 0, 0, 5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                              ("B. Reserve", "G", None, None, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]),
        _pl(1500, "Coventry City", [("R. Vance", "F", 67, "7.4", 1, 0, 3, 2, 1, 22, 15, 7, 4, 2, 0, 0, 2, 2, 0, 0),
                                    ("K. Osei", "M", 67, "6.8", 0, 1, 1, 1, 2, 40, 13, 6, 1, 0, 3, 1, 3, 1, 1, 0),
                                    ("D. Mills", "D", 64, "5.4", 0, 0, 0, 0, 0, 33, 9, 3, 0, 0, 2, 1, 4, 0, 1, 1),
                                    ("P. Njoku", "G", 67, "7.0", 0, 0, 0, 0, 0, 24, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0)]),
    ],
}


# Edge-case match: opening goal, missed penalty, own goal, second yellow, VAR, penalty, stoppage-time equalizer
EVENTS[1004] = [
    _ev(10, None, "Harbor FC", 700, "J. Marsh", "Goal", "Normal Goal"),
    _ev(25, None, "Ridgeline SC", 701, "C. Dunn", "Goal", "Missed Penalty"),
    _ev(38, None, "Harbor FC", 700, "T. Boyd", "Goal", "Own Goal"),
    _ev(44, None, "Ridgeline SC", 701, "N. Park", "Card", "Yellow Card"),
    _ev(52, None, "Ridgeline SC", 701, "N. Park", "Card", "Second Yellow card"),
    _ev(60, None, "Ridgeline SC", 701, "R. Aziz", "Var", "Goal Disallowed - offside"),
    _ev(71, None, "Harbor FC", 700, "J. Marsh", "Goal", "Penalty"),
    _ev(90, 3, "Ridgeline SC", 701, "R. Aziz", "Goal", "Normal Goal", "Z. Okoro"),
]