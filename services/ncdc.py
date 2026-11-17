"""
National Climatic Data Center (NCDC) client.

Responsible for historical CLIMATE data for a location.
API docs: https://www.ncdc.noaa.gov/cdo-web/webservices/v2

How it works:
    1. GET /stations near the coordinates that report monthly summaries (GSOM)
       - pick the closest one
    2. GET /data for that station's most recent 12 months
       - average temperature, average high/low, and total precipitation

Note: this API needs a free token, sent in a "token" header.
Request one at https://www.ncdc.noaa.gov/cdo-web/token
and put it in the NCDC_TOKEN environment variable before starting the app.
"""

import math
import os
from datetime import date

import requests

from services import REQUEST_TIMEOUT, USER_AGENT, ServiceError

NCDC_BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2"

# Global Summary of the Month: one row per station, month and measurement.
DATASET = "GSOM"

# NCDC measurement name -> name used in our report.
DATATYPES = {
    "TAVG": "avg_temp",
    "TMAX": "avg_high",
    "TMIN": "avg_low",
    "PRCP": "precip",
}

# How far (in degrees) to look for a station. Tried in order until one is found.
SEARCH_RADII = (0.25, 0.5, 1.0)

# Only consider stations that have reported within this many years.
RECENT_YEARS = 2


def get_climate(lat, lon):
    """Return a climate summary for the given coordinates as a dict."""
    token = os.environ.get("NCDC_TOKEN")
    if not token:
        raise ServiceError("NCDC_TOKEN is not set; NCDC needs an API token")

    station = _find_station(lat, lon, token)
    start, end = _last_twelve_months(station["maxdate"])
    rows = _get_json(
        "/data",
        token,
        {
            "datasetid": DATASET,
            "stationid": station["id"],
            "datatypeid": list(DATATYPES),
            "startdate": start.isoformat(),
            "enddate": end.isoformat(),
            "units": "standard",
            "limit": 1000,
        },
    ).get("results", [])

    if not rows:
        raise ServiceError(f"NCDC has no recent data for station {station['id']}")

    monthly = _format_monthly(rows)

    return {
        "source": "NCDC",
        "location": {"lat": lat, "lon": lon},
        "station": {
            "id": station["id"],
            "name": station.get("name"),
            "lat": station["latitude"],
            "lon": station["longitude"],
            "elevation_m": station.get("elevation"),
            "distance_km": round(station["distance_km"], 1),
        },
        "period": {"start": monthly[0]["month"], "end": monthly[-1]["month"]},
        "units": {"temperature": "F", "precipitation": "in"},
        "summary": _summarize(monthly),
        "monthly": monthly,
    }


def _get_json(path, token, params):
    """GET an NCDC endpoint and return the JSON body, or raise ServiceError."""
    headers = {"token": token, "User-Agent": USER_AGENT}
    try:
        response = requests.get(
            NCDC_BASE_URL + path, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as error:
        raise ServiceError(f"could not reach NCDC: {error}") from error

    if not response.ok:
        raise ServiceError(f"NCDC request failed: HTTP {response.status_code}")

    try:
        return response.json()
    except ValueError as error:
        raise ServiceError("NCDC returned a response that is not JSON") from error


def _find_station(lat, lon, token):
    """Return the closest recently active GSOM station, with a distance_km field."""
    recent = date.today().replace(year=date.today().year - RECENT_YEARS, day=1)

    for radius in SEARCH_RADII:
        corners = (lat - radius, lon - radius, lat + radius, lon + radius)
        extent = ",".join(f"{round(c, 4)}" for c in corners)
        stations = _get_json(
            "/stations",
            token,
            {
                "datasetid": DATASET,
                "datatypeid": "TAVG",
                "extent": extent,
                "startdate": recent.isoformat(),
                "limit": 1000,
            },
        ).get("results", [])

        if stations:
            for station in stations:
                station["distance_km"] = _distance_km(
                    lat, lon, station["latitude"], station["longitude"]
                )
            return min(stations, key=lambda s: s["distance_km"])

    raise ServiceError("NCDC has no active weather station near this location")


def _last_twelve_months(maxdate):
    """Return (start, end) dates covering the 12 months up to a station's maxdate."""
    end = date.fromisoformat(maxdate[:10]).replace(day=1)
    months = end.year * 12 + (end.month - 1) - 11
    start = date(months // 12, months % 12 + 1, 1)
    return start, end


def _format_monthly(rows):
    """Group NCDC rows (one per month per measurement) into one dict per month."""
    by_month = {}
    for row in rows:
        name = DATATYPES.get(row.get("datatype"))
        if name is None:
            continue
        month = row["date"][:7]  # "2025-10-01T00:00:00" -> "2025-10"
        entry = by_month.setdefault(month, {"month": month, **{n: None for n in DATATYPES.values()}})
        entry[name] = row.get("value")
    return [by_month[month] for month in sorted(by_month)]


def _summarize(monthly):
    """Average the monthly temperatures and add up the precipitation."""

    def values(field):
        return [m[field] for m in monthly if m[field] is not None]

    def average(field):
        found = values(field)
        return round(sum(found) / len(found), 1) if found else None

    precip = values("precip")
    return {
        "avg_temp": average("avg_temp"),
        "avg_high": average("avg_high"),
        "avg_low": average("avg_low"),
        "total_precip": round(sum(precip), 2) if precip else None,
        "months_with_data": len(monthly),
    }


def _distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in kilometers."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(a))
