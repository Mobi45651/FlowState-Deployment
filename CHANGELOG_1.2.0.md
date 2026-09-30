# SIH1.2.0 — Changelog

## New features
- **SOS button** (floating, every page): calls India's unified emergency
  number (112) directly, and optionally logs the request with GPS
  coordinates into the app's own alert feed. Does NOT contact real
  emergency services by itself — only the 112 call does that. See
  `backend/services/sos_service.py`.
- **Citizen photo reporting** (floating camera button, every page):
  upload a waterlogging photo with self-reported severity. Location is
  read from the photo's own EXIF GPS data if present, else your browser
  location, else a manually-picked zone. Reports are stored in the SAME
  `flood_events` table the ML training pipeline and each zone's
  historical-frequency label read from — so a real report genuinely
  feeds the dataset. **No image-recognition model inspects photo
  content** — this is EXIF geolocation + self-reported severity, not
  computer vision. See `backend/services/citizen_report_service.py`.
- **Street-level waterlogging** now has its own map layer toggle
  (previously bundled under "risk zones"), backed by a real endpoint
  (`GET /api/routes/geojson`) that colors each road segment by its
  parent zone's LIVE nowcast risk at the selected timestep.
- **Safe route is now actually drawn on the map** — dashed line for the
  normal route, solid green line for the flood-safe route (visually
  bent away from avoided high-risk zones), with start/end markers.
- **Map centering on the selected zone** now works on every page that
  embeds the map (previously worked on 2 of 4).

## Bugs fixed this release
- `useRouteGeoJSON` was called but didn't exist anywhere — hard crash on
  every page with a map. Now implemented end-to-end (hook + API call +
  backend endpoint).
- Safe route was hardcoded to show "LOW" risk whenever anything was
  avoided, even if a moderate-risk zone remained on the path — now
  reflects the actual worst remaining risk.
- Zone elevation was using Mumbai's coastal range (3-35m) after a
  Gurugram rename — mismatched both the ML model's training range
  (150-350m) and real Gurugram elevation (~213-250m). Fixed to 200-260m.
- Weather humidity (and to a lesser extent temp/wind) was reading from
  the current-HOUR FORECAST instead of Open-Meteo's true CURRENT
  conditions for a selected zone — now uses `current` first, matching
  what the geolocation-based weather view already did correctly.

## Setup changes required
1. **New Python dependency**: `Pillow` (EXIF GPS extraction) — see
   `requirements.txt`, run `pip install -r requirements.txt` again.
2. **Database schema changed**: `flood_events` table gained `photo_path`,
   `latitude`, `longitude`, `location_from_exif` columns, and `source`
   now also accepts `"citizen_report"`. This project has no formal
   migrations (`db.create_all()` only creates NEW tables, it won't alter
   an existing one) — **delete `flood_nowcasting.db` and re-run**:
   ```bash
   flask --app app init-db
   flask --app app seed-db
   ```
3. **New folder**: `backend/uploads/citizen_reports/` is created
   automatically on first photo upload — already gitignored.
