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

from report import get_report, report_failed

app = Flask(__name__)


@app.route("/report", methods=["GET"])
def report_route():
    # 1. Read the inputs from the URL, e.g. /report?lat=44.56&lon=-123.26&type=all
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    report_type = request.args.get("type", default="all")

    # 2. Check that we got usable coordinates.
    #    type=float above turns a missing or non-numeric value into None.
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required and must be numbers"}), 400

    #    Written as "not (in range)" so NaN and infinity are rejected too.
    if not -90 <= lat <= 90:
        return jsonify({"error": "lat must be between -90 and 90"}), 400
    if not -180 <= lon <= 180:
        return jsonify({"error": "lon must be between -180 and 180"}), 400

    # 3. Build the report and send it back.
    try:
        report = get_report(lat, lon, report_type)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    # 4. If no data source worked, tell the caller the upstream APIs failed.
    if report_failed(report):
        return jsonify(report), 502

    return jsonify(report)


if __name__ == "__main__":
    app.run(debug=True)
