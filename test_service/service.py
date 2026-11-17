"""
Dummy Flask program that calls the weather/climate report microservice.

Start the microservice first (it runs on port 5000), then run:
    python test_program.py
and open http://127.0.0.1:5001 in a browser.
"""

import requests
from flask import Flask, request, jsonify

MICROSERVICE_URL = "http://127.0.0.1:5000/report"

app = Flask(__name__)


@app.route("/")
def index():
    # Defaults to Corvallis, OR. Override with ?lat=..&lon=..&type=..
    params = {
        "lat": request.args.get("lat", 44.56),
        "lon": request.args.get("lon", -123.26),
        "type": request.args.get("type", "all"),
    }

    response = requests.get(MICROSERVICE_URL, params=params)
    data = response.json()

    print("Called:", response.url)
    print("Status:", response.status_code)

    return jsonify(data)


if __name__ == "__main__":
    app.run(port=5001)