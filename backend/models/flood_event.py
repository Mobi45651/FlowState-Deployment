"""
models/flood_event.py
-----------------------
Historical (or clearly-labeled demo) flood occurrences per zone. Three jobs:
1. Seeds the `historical_flood_frequency` label on Zone.
2. Supplies the `historical_flood_frequency` feature to ml/train.py.
3. Stores citizen-submitted waterlogging photo reports (source="citizen_report",
   see services/citizen_report_service.py) -- this is what feeds a real
   photo report into the same dataset the ML model's frequency feature reads.

`source` must always be "historical", "demo", or "citizen_report" -- never
blank -- so train.py and the frontend can always tell real records,
synthetic ones, and citizen-submitted ones apart.
"""

from extensions import db
from models.base import TimestampMixin


class FloodEvent(db.Model, TimestampMixin):
    __tablename__ = "flood_events"

    id = db.Column(db.Integer, primary_key=True)
    zone_id = db.Column(db.Integer, db.ForeignKey("zones.id"), nullable=False, index=True)
    event_date = db.Column(db.Date, nullable=False)

    severity = db.Column(db.String(10), nullable=False)  # LOW/MODERATE/HIGH/SEVERE
    water_depth_cm = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=True)

    source = db.Column(db.String(20), nullable=False, default="demo")  # "historical" / "demo" / "citizen_report"

    # Citizen photo reports only -- NULL for historical/demo rows.
    photo_path = db.Column(db.String(255), nullable=True)
    # Precise report location, which may differ from the zone's centroid --
    # from the photo's EXIF GPS tag if present, else the reporter's browser
    # geolocation. NULL for historical/demo rows (those only have a zone).
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    # Whether latitude/longitude came from the photo's own EXIF GPS data
    # (True) or the browser's geolocation API (False) -- shown in the UI
    # so nobody mistakes a device-reported location for the photo's own.
    location_from_exif = db.Column(db.Boolean, nullable=True)

    zone = db.relationship("Zone", back_populates="flood_events")

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "event_date": self.event_date.isoformat(),
            "severity": self.severity,
            "water_depth_cm": self.water_depth_cm,
            "description": self.description,
            "source": self.source,
            "photo_path": self.photo_path,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location_from_exif": self.location_from_exif,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<FloodEvent zone={self.zone_id} {self.event_date} {self.severity} ({self.source})>"
