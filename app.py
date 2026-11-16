"""
Flask entry point for the report microservice.

This file only handles HTTP: read the query parameters, call get_report(),
and send the result back as JSON. The report logic lives in report.py.

Run it with:
    python app.py

Then call it with:
    http://127.0.0.1:5000/report?lat=44.56&lon=-123.26&type=weather
"""

from flask import Flask, jsonify, request

from report import get_report

app = Flask(__name__)


@app.route("/report", methods=["GET"])
def report_route():
    # 1. Read the inputs from the URL, e.g. /report?lat=44.56&lon=-123.26&type=all
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    report_type = request.args.get("type", default="all")

    # 2. Check that we got usable coordinates.
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required numbers"}), 400

    # 3. Build the report and send it back.
    try:
        report = get_report(lat, lon, report_type)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify(report)


if __name__ == "__main__":
    app.run(debug=True)
