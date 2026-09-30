"""
app.py
-------
Application factory. Running `python app.py` starts the dev server; running
`flask --app app init-db` or `flask --app app seed-db` (CLI commands
registered below) sets up the database. Every later phase adds its
blueprint registration here and nowhere else.

Connects to:
- config.py       -> supplies the Config object
- extensions.py   -> db, cors get bound to this specific app here
- models/__init__ -> imported (indirectly, via database/init_db.py) so
                     db.create_all() knows about every table
- routes/__init__ -> register_blueprints(app) wires up every blueprint
"""

import os
from flask import Flask, jsonify
from sqlalchemy import event

from config import config_by_name
from extensions import db, cors


def create_app(env: str | None = None) -> Flask:
    env = env or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(env, config_by_name["development"]))

    # --- Bind extensions to this app instance ---
    # SQLite concurrency safeguards: wait for short-lived locks and enable WAL.
    db.init_app(app)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        with app.app_context():
            @event.listens_for(db.engine, "connect")
            def _configure_sqlite_connection(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA busy_timeout=60000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

            # WAL is persistent for file-backed databases and permits readers
            # while a writer is active. Skip for in-memory test databases.
            database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
            if ":memory:" not in database_uri:
                try:
                    with db.engine.connect() as connection:
                        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
                        connection.exec_driver_sql("PRAGMA synchronous=NORMAL")
                except Exception as exc:
                    app.logger.warning("Could not enable SQLite WAL mode: %s", exc)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["ALLOWED_ORIGINS"]}})
    # Origins come from ALLOWED_ORIGINS in .env (comma-separated). Defaults
    # to common local Vite/CRA dev ports so `npm run dev` works out of the
    # box. Set this to your actual deployed frontend URL(s) in production
    # -- see .env.example.

    # --- Register blueprints ---
    from routes import register_blueprints
    register_blueprints(app)

    # --- Friendly root route so visiting http://localhost:5000/ isn't a 404 ---
    @app.route("/")
    def index():
        return jsonify({
            "service": "SIH26085 Urban Flood Nowcasting System — Backend",
            "status": "running",
            "health_check": "/api/health",
        })

    # --- CLI commands: `flask --app app init-db` / `flask --app app seed-db` ---
    @app.cli.command("init-db")
    def init_db_command():
        """Create all tables (does not drop existing ones)."""
        from database.init_db import init_db
        init_db(app)
        print("Database tables created.")

    @app.cli.command("seed-db")
    def seed_db_command():
        """Populate demo zones, drains, rainfall, events, and roads."""
        from database.seed import seed_db
        seed_db(app)
        print("Database seeded with demo data.")

    @app.cli.command("run-pipeline")
    def run_pipeline_command():
        """Pull live weather (Open-Meteo) for every zone and store it.
        Falls back to clearly-labeled demo data per zone if the API call
        fails, instead of aborting the whole run."""
        from services.rainfall_pipeline import run_pipeline_for_all_zones
        with app.app_context():
            results = run_pipeline_for_all_zones()
        for r in results:
            tag = " [DEMO FALLBACK]" if r.get("used_demo_fallback") else ""
            print(f"{r['zone_code']}: {r['records_ingested']} records ({r['source']}){tag}")

    @app.cli.command("train-model")
    def train_model_command():
        """Trains the flood-risk Random Forest (on the synthetic demo
        dataset by default -- see ml/train.py for training on real data)."""
        from ml.train import train_model
        train_model()

    @app.cli.command("detect-blockages")
    def detect_blockages_command():
        """Runs the rule-based blockage estimator for every drain and
        writes a fresh (non-simulated) DrainReading for each."""
        from services.blockage_detector import detect_blockage_for_all_drains
        with app.app_context():
            results = detect_blockage_for_all_drains()
        for r in results:
            print(f"{r['drain_code']}: {r['estimated_blockage_percent']}% blocked -> {r['status']}")

    @app.cli.command("generate-alerts")
    def generate_alerts_command():
        """Checks every zone/drain against the alert thresholds and
        creates/resolves alerts accordingly."""
        from services.alert_service import generate_alerts_for_all_zones
        with app.app_context():
            created = generate_alerts_for_all_zones()
        print(f"{len(created)} new alert(s) created.")
        for a in created:
            print(f"  [{a.severity}] {a.alert_type} -- {a.message}")

    return app


# Allows `python app.py` for local development in addition to `flask run`.
if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=application.config["DEBUG"])
