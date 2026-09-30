"""
routes/alert_routes.py
--------------------------
GET /api/alerts                    -> regenerates alerts for every zone, then
                                       returns all currently ACTIVE alerts
GET /api/alerts?zone_id=<id>       -> same, filtered to one zone
GET /api/alerts?status=resolved    -> view resolved alerts instead

Regenerating on every call (rather than relying on a background job) keeps
this consistent with every other endpoint's "always live" pattern -- cheap
at this demo's scale (15 zones, a few dozen drains).
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Alert, Zone
from services.alert_service import generate_alerts_for_all_zones, generate_alerts_for_zone

alert_bp = Blueprint("alert", __name__)


@alert_bp.route("/alerts", methods=["GET"])
def list_alerts():
    zone_id = request.args.get("zone_id", type=int)
    status = request.args.get("status", default="active")

    if zone_id is not None:
        zone = Zone.query.get(zone_id)
        if zone is None:
            return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404
        generate_alerts_for_zone(zone)
    else:
        generate_alerts_for_all_zones()

    query = Alert.query
    if zone_id is not None:
        query = query.filter_by(zone_id=zone_id)
    if status in ("active", "resolved"):
        query = query.filter_by(status=status)

    alerts = query.order_by(Alert.created_at.desc()).all()

    return jsonify({
        "data": [a.to_dict() for a in alerts],
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200
