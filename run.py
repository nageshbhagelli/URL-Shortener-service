"""
Entry point for the URL Shortener Service.

Usage:
  python run.py                        # development
  FLASK_ENV=production python run.py   # production (use gunicorn in practice)

For production, run with gunicorn:
  gunicorn "run:app" --workers 4 --bind 0.0.0.0:5000
"""

import os
from app import create_app

app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    # debug=False in production — set via FLASK_ENV=production
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
