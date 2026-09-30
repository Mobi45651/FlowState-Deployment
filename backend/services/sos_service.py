"""
services/sos_service.py
---------------------------
Logs a citizen SOS request as an Alert (alert_type="SOS_REQUEST",
severity="SEVERE") tied to the nearest monitored zone -- reuses the
existing alerts table/UI rather than adding a whole new subsystem, so an
SOS immediately shows up wherever alerts are already displayed.

The Alert table has no lat/lng columns (see models/alert.py), so the
citizen's EXACT coordinates are embedded in the message text -- responders
need the precise point, not just "somewhere in this zone".

HONESTY NOTE: this logs a request into the app's own alert feed for
whoever is monitoring it. It is NOT a connection to any real emergency
dispatch service (police/fire/ambulance) -- the SOS button's "Call 112"
option (India's unified emergency number) is what actually reaches real
responders. Say this plainly in the UI, never imply this button alone
summons help.

Connects to:
- models/alert.py, models/zone.py -> what's read/written
- flood_engine/routing.py         -> haversine_distance_km() for nearest-zone lookup
- routes/sos_routes.py            -> exposes this over POST /api/sos
"""

from extensions import db
from models import Zone, Alert
from flood_engine.routing import haversine_distance_km


def _nearest_zone(latitude: float, longitude: float):
    closest, closest_km = None, None
    for zone in Zone.query.all():
        km = haversine_distance_km(latitude, longitude, zone.latitude, zone.longitude)
        if closest_km is None or km < closest_km:
            closest, closest_km = zone, km
    return closest, closest_km


def log_sos_request(latitude: float, longitude: float, message: str = "", contact: str = "") -> Alert:
    """Creates and returns the Alert row logging this SOS request. Raises
    ValueError if no zone exists in the system at all (empty DB) --
    callers should treat that as a 500-worthy setup problem, not a normal
    400, since a seeded deployment always has zones."""
    zone, distance_km = _nearest_zone(latitude, longitude)
    if zone is None:
        raise ValueError("No zones exist in the system -- has the database been seeded?")

    contact_line = f" Contact: {contact}." if contact else ""
    note_line = f" Note: {message}" if message else ""
    alert = Alert(
        zone_id=zone.id,
        alert_type="SOS_REQUEST",
        severity="SEVERE",
        message=(
            f"SOS request at {latitude:.5f}, {longitude:.5f} "
            f"(~{distance_km:.1f} km from {zone.name}).{contact_line}{note_line}"
        ),
        recommended_action="Dispatch assistance to the reported coordinates immediately.",
        status="active",
    )
    db.session.add(alert)
    db.session.commit()
    return alert
