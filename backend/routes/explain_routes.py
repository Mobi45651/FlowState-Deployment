"""
routes/explain_routes.py
----------------------------
GET /api/explain/<zone_id> -> the current ("NOW" step) explainability
breakdown for a zone: per-factor severity bars, a plain-language sentence,
and an honesty disclaimer (see ml/explain.py for the full reasoning).

Reuses build_zone_nowcast() rather than a separate code path, so
/api/explain can never disagree with /api/nowcast or /api/flood-risk about
the current prediction.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify

from models import Zone
from services.nowcast_engine import build_zone_nowcast
from ml.explain import build_explanation
from ml.predict import get_feature_importances

explain_bp = Blueprint("explain", __name__)


@explain_bp.route("/explain/<int:zone_id>", methods=["GET"])
def get_explanation(zone_id):
    zone = Zone.query.get(zone_id)
    if zone is None:
        return jsonify({"data": None, "error": f"No zone with id {zone_id}"}), 404

    result = build_zone_nowcast(zone)
    now_step = result["forecast"][0]

    explanation = build_explanation(
        feature_vector=now_step["feature_vector"],
        flood_probability=now_step["flood_probability"],
        risk_category=now_step["risk_category"],
        feature_importances=get_feature_importances(),
    )

    return jsonify({
        "data": {
            "zone_id": zone.id,
            "zone_code": zone.zone_code,
            "zone_name": zone.name,
            "model_version": now_step["model_version"],
            **explanation,
        },
        "meta": {"source": "computed", "generated_at": datetime.now(timezone.utc).isoformat()},
    }), 200
