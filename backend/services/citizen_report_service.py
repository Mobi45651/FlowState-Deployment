"""
services/citizen_report_service.py
-------------------------------------
Handles citizen-submitted waterlogging photo reports: saves the photo,
determines a location for it, assigns it to the nearest zone, and stores
it as a FloodEvent row with source="citizen_report" -- the SAME table
ml/train.py and each zone's historical_flood_frequency label already
read from, so a real citizen report genuinely feeds into the dataset the
system predicts from, not a side channel that goes nowhere.

HONESTY NOTE -- read this before describing the feature to anyone:
There is NO computer-vision model here that looks at the photo's CONTENT
and detects flooding. That would need a trained image-classification
model and a labeled dataset of real flood photos, neither of which
exists in this prototype (and none is downloaded here -- no network
access was used to fetch one). What IS real:
- EXIF GPS extraction straight from the photo file, when present (most
  phone camera photos have this if location services were on at the time)
- The citizen's OWN self-reported severity and description
"The system checks the photo's location" means EXIF geolocation +
nearest-zone lookup -- not image content analysis. Say so plainly in any
judge-facing description; do not call this "AI-verified flooding".

Connects to:
- models/flood_event.py       -> where every report is stored
- flood_engine/routing.py     -> haversine_distance_km() for nearest-zone lookup
- routes/report_routes.py     -> exposes this over POST/GET /api/reports
"""

import os
import uuid
from datetime import date

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from flask import current_app

from extensions import db
from models import Zone, FloodEvent
from flood_engine.routing import haversine_distance_km

VALID_SEVERITIES = ("LOW", "MODERATE", "HIGH", "SEVERE")


class CitizenReportError(Exception):
    """Raised for any submission that can't be processed -- the route
    catches this and returns a 400 with the message, never a 500."""


def _allowed_extension(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]


def _dms_to_decimal(dms, ref) -> float:
    """EXIF GPS stores coordinates as (degrees, minutes, seconds) --
    converts that to a single decimal-degrees value, negated for the
    Southern/Western hemispheres."""
    degrees, minutes, seconds = dms
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_exif_gps(file_path: str):
    """Returns (latitude, longitude) from the photo's own EXIF GPS tags,
    or None if it has none -- very common, since many messaging apps strip
    EXIF on send and many phones have photo geotagging turned off. Never
    raises: a photo that can't be parsed simply yields no GPS, exactly
    like one that was never geotagged."""
    try:
        image = Image.open(file_path)
        exif_raw = image._getexif()
        if not exif_raw:
            return None

        exif = {TAGS.get(k, k): v for k, v in exif_raw.items()}
        gps_info = exif.get("GPSInfo")
        if not gps_info:
            return None

        gps = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}
        lat, lat_ref = gps.get("GPSLatitude"), gps.get("GPSLatitudeRef")
        lng, lng_ref = gps.get("GPSLongitude"), gps.get("GPSLongitudeRef")
        if not (lat and lat_ref and lng and lng_ref):
            return None

        return (_dms_to_decimal(lat, lat_ref), _dms_to_decimal(lng, lng_ref))
    except Exception:
        return None


def _nearest_zone(latitude: float, longitude: float):
    """Returns (zone, distance_km) for the closest seeded zone, or
    (None, distance) if even the closest one is farther than
    MAX_REPORT_ZONE_DISTANCE_KM -- a report from a different city
    shouldn't be silently filed under whatever zone is least-far-away."""
    max_km = current_app.config["MAX_REPORT_ZONE_DISTANCE_KM"]
    closest, closest_km = None, None
    for zone in Zone.query.all():
        km = haversine_distance_km(latitude, longitude, zone.latitude, zone.longitude)
        if closest_km is None or km < closest_km:
            closest, closest_km = zone, km
    if closest is None or closest_km > max_km:
        return None, closest_km
    return closest, closest_km


def submit_citizen_report(
    photo_file, severity: str, description: str = "",
    browser_lat: float = None, browser_lng: float = None, zone_id: int = None,
) -> FloodEvent:
    """Resolves a location in this priority order:
    1. An explicit zone_id (citizen manually picked a zone)
    2. EXIF GPS pulled from the photo itself
    3. Browser geolocation submitted alongside the upload
    Raises CitizenReportError with a user-facing message on any failure;
    never leaves an orphaned file behind on failure paths after saving."""
    if not photo_file or not photo_file.filename:
        raise CitizenReportError("No photo was included in this report.")
    if not _allowed_extension(photo_file.filename):
        raise CitizenReportError("Photo must be JPG, PNG, WEBP, or HEIC.")
    if severity not in VALID_SEVERITIES:
        raise CitizenReportError(f"severity must be one of {', '.join(VALID_SEVERITIES)}.")

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    ext = photo_file.filename.rsplit(".", 1)[-1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    stored_path = os.path.join(upload_dir, stored_name)
    photo_file.save(stored_path)

    zone, latitude, longitude, location_from_exif = None, None, None, None

    if zone_id is not None:
        zone = Zone.query.get(zone_id)
        if zone is None:
            os.remove(stored_path)
            raise CitizenReportError(f"No zone with id {zone_id}.")
        latitude, longitude, location_from_exif = zone.latitude, zone.longitude, False
    else:
        exif_gps = extract_exif_gps(stored_path)
        if exif_gps:
            latitude, longitude, location_from_exif = exif_gps[0], exif_gps[1], True
        elif browser_lat is not None and browser_lng is not None:
            latitude, longitude, location_from_exif = browser_lat, browser_lng, False
        else:
            os.remove(stored_path)
            raise CitizenReportError(
                "Couldn't determine a location for this report -- the photo has no "
                "GPS data and no location was provided. Enable location access or "
                "pick a zone manually."
            )
        zone, distance_km = _nearest_zone(latitude, longitude)
        if zone is None:
            os.remove(stored_path)
            raise CitizenReportError(
                f"This location is too far ({distance_km:.0f} km) from any monitored zone."
            )

    report = FloodEvent(
        zone_id=zone.id, event_date=date.today(), severity=severity,
        description=description or None, source="citizen_report",
        photo_path=stored_name, latitude=latitude, longitude=longitude,
        location_from_exif=location_from_exif,
    )
    db.session.add(report)
    db.session.commit()
    return report


def list_recent_reports(zone_id: int = None, limit: int = 50):
    query = FloodEvent.query.filter_by(source="citizen_report")
    if zone_id is not None:
        query = query.filter_by(zone_id=zone_id)
    return query.order_by(FloodEvent.created_at.desc()).limit(limit).all()
