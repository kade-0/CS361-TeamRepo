"""
National Weather Service (NWS) client.

Responsible for current / forecast WEATHER for a location.
API docs: https://www.weather.gov/documentation/services-web-api

How it works:
    1. GET https://api.weather.gov/points/{lat},{lon}
       - the response tells us which forecast URL covers this location
    2. GET that forecast URL
       - the response holds the forecast periods we want

NWS only covers the United States and its territories.
"""

import requests

from services import REQUEST_TIMEOUT, USER_AGENT, ServiceError

NWS_BASE_URL = "https://api.weather.gov"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/geo+json",
}


def get_weather(lat, lon):
    """Return a weather summary for the given coordinates as a dict."""
    # NWS wants at most 4 decimal places in the points URL.
    points = _get_json(f"{NWS_BASE_URL}/points/{lat:.4f},{lon:.4f}")
    point_props = points.get("properties", {})

    forecast_url = point_props.get("forecast")
    if not forecast_url:
        raise ServiceError("NWS has no forecast for this location")

    forecast = _get_json(forecast_url)
    forecast_props = forecast.get("properties", {})

    return {
        "source": "NWS",
        "location": {"lat": lat, "lon": lon},
        "place": _format_place(point_props),
        "updated": forecast_props.get("updateTime"),
        "forecast": [_format_period(p) for p in forecast_props.get("periods", [])],
    }


def _get_json(url):
    """GET a URL from NWS and return the JSON body, or raise ServiceError."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as error:
        raise ServiceError(f"could not reach NWS: {error}") from error

    if not response.ok:
        # NWS error bodies usually explain the problem in "detail".
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        message = detail or f"HTTP {response.status_code}"
        raise ServiceError(f"NWS request failed: {message}")

    try:
        return response.json()
    except ValueError as error:
        raise ServiceError("NWS returned a response that is not JSON") from error


def _format_place(point_props):
    """Turn the points response into {"city": ..., "state": ...}, or None."""
    relative = point_props.get("relativeLocation", {}).get("properties", {})
    if not relative:
        return None
    return {"city": relative.get("city"), "state": relative.get("state")}


def _format_period(period):
    """Keep only the useful fields of one NWS forecast period."""
    precip = period.get("probabilityOfPrecipitation") or {}
    wind = " ".join(
        part for part in (period.get("windSpeed"), period.get("windDirection")) if part
    )
    return {
        "name": period.get("name"),
        "start": period.get("startTime"),
        "end": period.get("endTime"),
        "is_daytime": period.get("isDaytime"),
        "temperature": period.get("temperature"),
        "temperature_unit": period.get("temperatureUnit"),
        "precip_chance_percent": precip.get("value"),
        "wind": wind or None,
        "summary": period.get("shortForecast"),
        "details": period.get("detailedForecast"),
    }
