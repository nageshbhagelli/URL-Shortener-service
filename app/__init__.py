"""
URL Shortener Service - Application Factory
"""

import os
from flask import Flask
from .config import get_config
from .database import init_db
from .routes import register_routes


def create_app(config_name: str = None) -> Flask:
    """
    Application factory pattern - allows creating multiple app instances
    (useful for testing and multi-environment deployments).
    """
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    # Load config based on environment
    config = get_config(config_name or os.getenv("FLASK_ENV", "development"))
    app.config.from_object(config)

    # Initialize DB (creates tables if not present)
    init_db(app)

    # Register all route blueprints
    register_routes(app)

    return app
