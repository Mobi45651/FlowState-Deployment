"""
routes/nowcast_routes.py
---------------------------
GET /api/nowcast                        -> 7-step forecast for every zone
GET /api/nowcast/<zone_id>               -> 7-step forecast for one zone
GET /api/nowcast/<zone_id>?refresh=1     -> force a fresh Open-Meteo pull
                                             before building the nowcast

Response shape matches the architecture doc's example:
{"zone_id": ..., "forecast": [{"time": "18:00", "rainfall_mm": ..., ...}]}

All the real work happens in services/nowcast_engine.py -- this file only
parses the request and shapes the JSON envelope.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify, request

from models import Zone
from services.nowcast_engine import build_zone_nowcast, build_all_zones_nowcast
from services.rainfall_pipeline import ingest_zone_rainfall, run_pipeline_for_all_zones

nowcast_bp = Blueprint("nowcast", __name__)


@nowcast_bp.route("/nowcast", methods=["GET"])
def get_nowcast_all():
    if request.args.get("refresh", "0") in ("1", "true", "True"):
        run_pipeline_for_all_zones()

    results = build_all_zones_nowcast()
    return jsonify({
        "data": results,
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200


@nowcast_bp.route("/nowcast/<int:zone_id>", methods=["GET"])
def get_nowcast_zone(zone_id):
    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    if request.args.get("refresh", "0") in ("1", "true", "True"):
        ingest_zone_rainfall(zone, force_refresh=True)

    result = build_zone_nowcast(zone)
    return jsonify({
        "data": result,
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200
