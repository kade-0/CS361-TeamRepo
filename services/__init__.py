# Each module in this package talks to one outside data source.

# Sent with every outgoing request. NWS rejects requests without a User-Agent.
USER_AGENT = "CS361-WeatherReport/1.0"

# Seconds to wait for an outside API before giving up.
REQUEST_TIMEOUT = 10


class ServiceError(Exception):
    """An outside data source could not give us the data we asked for."""
