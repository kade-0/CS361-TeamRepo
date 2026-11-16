"""
Builds a report by combining the data sources.

Answers "given a location and a report type, what data goes in the report?"
"""

from services.nws import get_weather
from services.ncdc import get_climate

VALID_REPORT_TYPES = ("all", "weather", "climate")


def get_report(lat, lon, report_type="all"):
    """
    Build a report for one location.

    report_type can be:
        "weather" -> NWS data only
        "climate" -> NCDC data only
        "all"     -> both
    """
    if report_type not in VALID_REPORT_TYPES:
        raise ValueError(f"report_type must be one of {VALID_REPORT_TYPES}")

    report = {
        "location": {"lat": lat, "lon": lon},
        "report_type": report_type,
    }

    if report_type in ("all", "weather"):
        report["weather"] = get_weather(lat, lon)

    if report_type in ("all", "climate"):
        report["climate"] = get_climate(lat, lon)

    return report
