"""
routes/sos_routes.py
------------------------
POST /api/sos
Body: {"latitude": .., "longitude": .., "message": "optional", "contact": "optional"}

Logs the request as a SEVERE alert (see services/sos_service.py for
exactly what this does and doesn't do -- it does NOT contact real
emergency services on its own).
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from services.sos_service import log_sos_request

sos_bp = Blueprint("sos", __name__)


@sos_bp.route("/sos", methods=["POST"])
def post_sos():
    body = request.get_json(silent=True) or {}

    try:
        latitude = float(body.get("latitude"))
        longitude = float(body.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({
            "data": None,
            "error": "Request body must include numeric 'latitude' and 'longitude'.",
        }), 400

    message = (body.get("message") or "")[:500]
    contact = (body.get("contact") or "")[:120]

    try:
        alert = log_sos_request(latitude, longitude, message=message, contact=contact)
    except ValueError as exc:
        return jsonify({"data": None, "error": str(exc)}), 500

    return jsonify({
        "data": alert.to_dict(),
        "meta": {"source": "sos", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 201
