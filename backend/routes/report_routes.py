"""
routes/report_routes.py
---------------------------
POST /api/reports  (multipart/form-data)
    Fields: photo (file, required), severity (required: LOW/MODERATE/HIGH/SEVERE),
    description (optional), latitude/longitude (optional -- browser geolocation
    fallback if the photo has no EXIF GPS), zone_id (optional -- manual override)

GET /api/reports?zone_id=<id>          -> recent citizen reports
GET /api/reports/photo/<filename>      -> serves an uploaded photo

All the real logic lives in services/citizen_report_service.py -- see that
file's module docstring for exactly what "location checking" does and
does NOT mean here (no image-content flood detection).
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, send_from_directory, current_app

from services.citizen_report_service import (
    submit_citizen_report, list_recent_reports, CitizenReportError,
)

report_bp = Blueprint("report", __name__)


@report_bp.route("/reports", methods=["POST"])
def create_report():
    photo = request.files.get("photo")
    severity = (request.form.get("severity") or "").upper()
    description = request.form.get("description", "")

    def _optional_float(name):
        value = request.form.get(name)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except ValueError:
            return None

    browser_lat = _optional_float("latitude")
    browser_lng = _optional_float("longitude")
    zone_id = request.form.get("zone_id", type=int)

    try:
        report = submit_citizen_report(
            photo_file=photo, severity=severity, description=description,
            browser_lat=browser_lat, browser_lng=browser_lng, zone_id=zone_id,
        )
    except CitizenReportError as exc:
        return jsonify({"data": None, "error": str(exc)}), 400

    return jsonify({
        "data": report.to_dict(),
        "meta": {"source": "citizen_report", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 201


@report_bp.route("/reports", methods=["GET"])
def get_reports():
    zone_id = request.args.get("zone_id", type=int)
    limit = request.args.get("limit", default=50, type=int)
    reports = list_recent_reports(zone_id=zone_id, limit=min(limit, 200))

    return jsonify({
        "data": [r.to_dict() for r in reports],
        "meta": {"source": "database", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@report_bp.route("/reports/photo/<path:filename>", methods=["GET"])
def get_report_photo(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
