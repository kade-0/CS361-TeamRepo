# Weather and Climate Reports

A weather and climate report fetching microservice built with Flask.

Give it a latitude and longitude, and it returns a JSON report built from:

- **NWS** (National Weather Service): weather forecast
- **NCDC** (NOAA Climate Data Online): historical climate data

## File structure

```
app.py              Flask app: reads the request, returns JSON
report.py           get_report(): decides which data goes in the report
services/
    nws.py          get_weather(): talks to the NWS API
    ncdc.py         get_climate(): talks to the NCDC API
requirements.txt    Python packages needed
```

A request moves through the files like this:

```
HTTP request -> app.py -> report.py -> services/nws.py and/or services/ncdc.py
```

## Setup

```
pip install -r requirements.txt
python app.py
```

## Usage

```
GET /report?lat=<latitude>&lon=<longitude>&type=<all|weather|climate>
```

`type` is optional and defaults to `all`.

Example:

```
http://127.0.0.1:5000/report?lat=44.56&lon=-123.26&type=weather
```

Example response:

```json
{
  "location": {"lat": 44.56, "lon": -123.26},
  "report_type": "weather",
  "weather": {
    "source": "NWS",
    "location": {"lat": 44.56, "lon": -123.26},
    "forecast": []
  }
}
```

A missing `lat`/`lon` or an unknown `type` returns a `400` with an `error` message.

## Status

- [x] Basic Flask app and file structure
- [ ] Real NWS requests in `services/nws.py`
- [ ] Real NCDC requests in `services/ncdc.py` (needs a free API token)
- [ ] Format the API responses into a clean report
