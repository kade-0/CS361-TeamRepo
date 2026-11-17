"""
Builds a report by combining the data sources.

Answers "given a location and a report type, what data goes in the report?"
"""

from services import ServiceError
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

    If a data source fails, its section holds {"source": ..., "error": ...}
    instead of data, so one failing source does not hide the other.

    Raises ValueError if report_type is not one of VALID_REPORT_TYPES.
    """
    if report_type not in VALID_REPORT_TYPES:
        raise ValueError(
            f"Invalid report_type {report_type!r}; "
            f"must be one of {VALID_REPORT_TYPES}"
        )

    report = {
        "location": {"lat": lat, "lon": lon},
        "report_type": report_type,
    }

    if report_type in ("all", "weather"):
        report["weather"] = _safe_fetch("NWS", get_weather, lat, lon)

    if report_type in ("all", "climate"):
        report["climate"] = _safe_fetch("NCDC", get_climate, lat, lon)

    return report


def report_failed(report):
    """True if every section the report asked for came back as an error."""
    sections = [report[key] for key in ("weather", "climate") if key in report]
    return all("error" in section for section in sections)


def _safe_fetch(source, fetch, lat, lon):
    """
    Call fetch(lat, lon) and return its data. If the service raises a
    ServiceError, return {"source": source, "error": <message>} instead.

    Only ServiceError is caught, so genuine bugs (TypeError, KeyError, etc.)
    still surface instead of being silently turned into error sections.
    """
    try:
        return fetch(lat, lon)
    except ServiceError as exc:
        return {"source": source, "error": str(exc)}
