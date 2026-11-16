"""
National Climatic Data Center (NCDC) client.

Responsible for historical CLIMATE data for a location.
API docs: https://www.ncdc.noaa.gov/cdo-web/webservices/v2

Note: this API needs a free token, sent in a "token" header.
Request one at https://www.ncdc.noaa.gov/cdo-web/token
"""

NCDC_BASE_URL = "https://www.ncei.noaa.gov/cdo-web/api/v2"


def get_climate(lat, lon):
    """Return a climate summary for the given coordinates as a dict."""
    # TODO: replace this placeholder with real NCDC requests
    #       (find a nearby station, then fetch its climate data).
    return {
        "source": "NCDC",
        "location": {"lat": lat, "lon": lon},
        "climate": {},
    }
