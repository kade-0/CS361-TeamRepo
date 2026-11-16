"""
National Weather Service (NWS) client.

Responsible for current / forecast WEATHER for a location.
API docs: https://www.weather.gov/documentation/services-web-api

TODO:
    1. GET https://api.weather.gov/points/{lat},{lon}
       - the response tells us which forecast URL covers this location
    2. GET that forecast URL
       - the response holds the forecast periods we want
"""

NWS_BASE_URL = "https://api.weather.gov"


def get_weather(lat, lon):
    """Return a weather summary for the given coordinates as a dict."""
    # TODO: replace this placeholder with the two NWS requests described above.
    return {
        "source": "NWS",
        "location": {"lat": lat, "lon": lon},
        "forecast": [],
    }
