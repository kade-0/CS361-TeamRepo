"""Data providers. Both return the 'response' list in API-Football v3 format, so the
analysis code is identical for real and mock data."""
import os
import time
import requests

BASE_URL = "https://v3.football.api-sports.io"
PLACEHOLDER = "YOUR_API_FOOTBALL_KEY_HERE"
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}


class ProviderError(Exception):
    """Raised when the upstream data source fails. Carries an HTTP status for our own response."""
    def __init__(self, code, message, status=502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class ApiFootball:
    name = "api-football"

    def __init__(self, key, ttl=10, session=None, base_url=BASE_URL):
        self._key, self._ttl, self._base = key, ttl, base_url
        self._session = session or requests
        self._cache = {}

    def _get(self, path, params):
        cache_key = (path, tuple(sorted(params.items())))
        hit = self._cache.get(cache_key)
        if hit and hit[0] > time.time():
            return hit[1]
        try:
            r = self._session.get(self._base + path, params=params, timeout=5,
                                  headers={"x-apisports-key": self._key})
        except requests.RequestException:
            raise ProviderError("upstream_unreachable", "Could not reach API-Football.", 502)
        if r.status_code != 200:
            raise ProviderError("upstream_error", f"API-Football returned HTTP {r.status_code}.", 502)
        data = r.json()
        errors = data.get("errors")
        if errors:   # API-Football reports many problems as HTTP 200 with an 'errors' field
            text = str(errors).lower()
            if "rate" in text or "request" in text:
                raise ProviderError("rate_limited", "API-Football request limit reached. Try again later.", 429)
            if "token" in text or "key" in text:
                raise ProviderError("upstream_auth", "API-Football rejected the configured API key.", 502)
            raise ProviderError("upstream_error", "API-Football reported an error.", 502)
        self._cache[cache_key] = (time.time() + self._ttl, data.get("response", []))
        return self._cache[cache_key][1]

    def live_fixtures(self):
        return self._get("/fixtures", {"live": "all"})

    def fixture(self, fid):
        rows = self._get("/fixtures", {"id": fid})
        return rows[0] if rows else None

    def statistics(self, fid):
        return self._get("/fixtures/statistics", {"fixture": fid})

    def events(self, fid):
        return self._get("/fixtures/events", {"fixture": fid})


class MockProvider:
    name = "mock"

    def __init__(self):
        import mock_data
        self._d = mock_data

    def live_fixtures(self):
        return [f for f in self._d.FIXTURES.values() if f["fixture"]["status"]["short"] in LIVE_STATUSES]

    def fixture(self, fid):
        return self._d.FIXTURES.get(fid)

    def statistics(self, fid):
        return self._d.STATISTICS.get(fid, [])

    def events(self, fid):
        return self._d.EVENTS.get(fid, [])


def get_provider():
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if os.environ.get("USE_MOCK") == "1" or not key or key == PLACEHOLDER:
        return MockProvider()
    return ApiFootball(key, ttl=int(os.environ.get("CACHE_TTL", "10")))
