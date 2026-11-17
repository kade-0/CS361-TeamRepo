"""
Tests for the /report endpoint.

The NWS and NCDC clients are replaced with fakes, so these tests make no
network calls and do not need an NCDC_TOKEN.

Run from the project root with:
    python -m unittest -v
"""

import unittest
from unittest.mock import patch

from app import app
from services import ServiceError

LAT, LON = 44.56, -123.26

FAKE_WEATHER = {
    "source": "NWS",
    "location": {"lat": LAT, "lon": LON},
    "place": {"city": "Corvallis", "state": "OR"},
    "updated": "2026-11-16T23:41:19+00:00",
    "forecast": [{"name": "This Afternoon", "temperature": 53}],
}

FAKE_CLIMATE = {
    "source": "NCDC",
    "location": {"lat": LAT, "lon": LON},
    "station": {"id": "GHCND:USC00351862"},
    "summary": {"avg_temp": 53.1, "months_with_data": 12},
    "monthly": [{"month": "2025-10", "avg_temp": 54.3}],
}


class ReportTestCase(unittest.TestCase):
    """Starts each test with fake data sources and a Flask test client."""

    def setUp(self):
        # report.py imported get_weather/get_climate by name, so patch them there.
        weather_patch = patch("report.get_weather", return_value=FAKE_WEATHER)
        climate_patch = patch("report.get_climate", return_value=FAKE_CLIMATE)
        self.get_weather = weather_patch.start()
        self.get_climate = climate_patch.start()
        self.addCleanup(weather_patch.stop)
        self.addCleanup(climate_patch.stop)

        self.client = app.test_client()

    def get(self, query):
        return self.client.get(f"/report?{query}")

    def fail_weather(self):
        self.get_weather.side_effect = ServiceError("could not reach NWS")

    def fail_climate(self):
        self.get_climate.side_effect = ServiceError("could not reach NCDC")


class TestReportTypes(ReportTestCase):
    def test_weather_report(self):
        response = self.get(f"lat={LAT}&lon={LON}&type=weather")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["report_type"], "weather")
        self.assertEqual(body["location"], {"lat": LAT, "lon": LON})
        self.assertEqual(body["weather"], FAKE_WEATHER)
        self.assertNotIn("climate", body)
        self.get_weather.assert_called_once_with(LAT, LON)
        self.get_climate.assert_not_called()

    def test_climate_report(self):
        response = self.get(f"lat={LAT}&lon={LON}&type=climate")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["report_type"], "climate")
        self.assertEqual(body["location"], {"lat": LAT, "lon": LON})
        self.assertEqual(body["climate"], FAKE_CLIMATE)
        self.assertNotIn("weather", body)
        self.get_climate.assert_called_once_with(LAT, LON)
        self.get_weather.assert_not_called()

    def test_all_report(self):
        response = self.get(f"lat={LAT}&lon={LON}&type=all")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["report_type"], "all")
        self.assertEqual(body["location"], {"lat": LAT, "lon": LON})
        self.assertEqual(body["weather"], FAKE_WEATHER)
        self.assertEqual(body["climate"], FAKE_CLIMATE)
        self.get_weather.assert_called_once_with(LAT, LON)
        self.get_climate.assert_called_once_with(LAT, LON)

    def test_type_defaults_to_all(self):
        response = self.get(f"lat={LAT}&lon={LON}")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["report_type"], "all")
        self.assertIn("weather", body)
        self.assertIn("climate", body)

    def test_unknown_type_rejected(self):
        for report_type in ("forecast", "WEATHER", ""):
            with self.subTest(type=report_type):
                response = self.get(f"lat={LAT}&lon={LON}&type={report_type}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())
        self.get_weather.assert_not_called()
        self.get_climate.assert_not_called()


class TestSourceFailures(ReportTestCase):
    def test_weather_report_fails_with_502(self):
        self.fail_weather()

        response = self.get(f"lat={LAT}&lon={LON}&type=weather")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json()["weather"],
            {"source": "NWS", "error": "could not reach NWS"},
        )

    def test_climate_report_fails_with_502(self):
        self.fail_climate()

        response = self.get(f"lat={LAT}&lon={LON}&type=climate")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json()["climate"],
            {"source": "NCDC", "error": "could not reach NCDC"},
        )

    def test_all_report_fails_with_502_when_both_sources_fail(self):
        self.fail_weather()
        self.fail_climate()

        response = self.get(f"lat={LAT}&lon={LON}&type=all")

        self.assertEqual(response.status_code, 502)
        body = response.get_json()
        self.assertIn("error", body["weather"])
        self.assertIn("error", body["climate"])

    def test_all_report_succeeds_when_only_weather_fails(self):
        self.fail_weather()

        response = self.get(f"lat={LAT}&lon={LON}&type=all")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["weather"], {"source": "NWS", "error": "could not reach NWS"})
        self.assertEqual(body["climate"], FAKE_CLIMATE)

    def test_all_report_succeeds_when_only_climate_fails(self):
        self.fail_climate()

        response = self.get(f"lat={LAT}&lon={LON}&type=all")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["weather"], FAKE_WEATHER)
        self.assertEqual(body["climate"], {"source": "NCDC", "error": "could not reach NCDC"})


class TestCoordinateValidation(ReportTestCase):
    def assert_rejected(self, query):
        response = self.get(query)
        self.assertEqual(response.status_code, 400, query)
        self.assertIn("error", response.get_json())
        # Bad input must be caught before any outside API is called.
        self.get_weather.assert_not_called()
        self.get_climate.assert_not_called()

    def test_missing_coordinates(self):
        for query in ("", f"lon={LON}", f"lat={LAT}", "type=weather"):
            with self.subTest(query=query):
                self.assert_rejected(query)

    def test_non_numeric_coordinates(self):
        for query in (f"lat=abc&lon={LON}", f"lat={LAT}&lon=xyz", "lat=&lon="):
            with self.subTest(query=query):
                self.assert_rejected(query)

    def test_out_of_range_coordinates(self):
        for query in (
            f"lat=90.1&lon={LON}",
            f"lat=-90.1&lon={LON}",
            f"lat={LAT}&lon=180.1",
            f"lat={LAT}&lon=-180.1",
        ):
            with self.subTest(query=query):
                self.assert_rejected(query)

    def test_nan_and_infinity_rejected(self):
        for query in (f"lat=nan&lon={LON}", f"lat={LAT}&lon=inf", f"lat=-inf&lon={LON}"):
            with self.subTest(query=query):
                self.assert_rejected(query)

    def test_boundary_coordinates_accepted(self):
        for lat, lon in ((90, 180), (-90, -180), (0, 0)):
            with self.subTest(lat=lat, lon=lon):
                response = self.get(f"lat={lat}&lon={lon}&type=weather")
                self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
