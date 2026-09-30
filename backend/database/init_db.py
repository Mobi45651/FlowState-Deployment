"""
database/init_db.py
---------------------
Creates tables and applies small, additive SQLite schema migrations.
Safe to run repeatedly; existing flood-event rows are preserved.
"""

from flask import Flask
from sqlalchemy import inspect
from extensions import db
import models  # noqa: F401 -- registers every model with db.metadata


def migrate_existing_schema() -> None:
    """Add columns introduced after an older SQLite database was created."""
    inspector = inspect(db.engine)
    if "flood_events" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("flood_events")}
    additions = {
        "photo_path": "VARCHAR(255)",
        "latitude": "FLOAT",
        "longitude": "FLOAT",
        "location_from_exif": "BOOLEAN",
    }
    with db.engine.begin() as connection:
        for column_name, column_type in additions.items():
            if column_name not in existing:
                connection.exec_driver_sql(
                    f'ALTER TABLE flood_events ADD COLUMN "{column_name}" {column_type}'
                )
                print(f"Added flood_events.{column_name}")


def init_db(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        # create_all does not add columns to existing tables; run additive migration.
        migrate_existing_schema()

        # Create the judge/demo admin account if it does not exist.
        from models import User
        email = app.config["ADMIN_EMAIL"]
        if User.query.filter_by(email=email).first() is None:
            admin = User(
                username=app.config["ADMIN_USERNAME"],
                email=email,
                role="admin",
            )
            admin.set_password(app.config["ADMIN_PASSWORD"])
            db.session.add(admin)
            db.session.commit()
            print(f"Created admin account: {email}")


if __name__ == "__main__":
    from app import create_app
    application = create_app()
    init_db(application)
    print("Database tables created and migrations checked.")
