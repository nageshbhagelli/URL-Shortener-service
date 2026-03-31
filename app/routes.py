"""
Routes / Controllers — HTTP layer only.

No business logic here. Each route:
  1. Extracts inputs from request
  2. Calls service
  3. Returns HTTP response
"""

from flask import Blueprint, request, jsonify, redirect, abort, render_template, current_app

from . import services, repository

api = Blueprint("api", __name__)
ui = Blueprint("ui", __name__)


# ─── UI Route ──────────────────────────────────────────────────────────────────

@ui.route("/")
def index():
    return render_template("index.html")


# ─── POST /shorten ─────────────────────────────────────────────────────────────

@api.route("/shorten", methods=["POST"])
def shorten():
    """
    Accept a long URL and return a short URL.

    Body (JSON or form):
      long_url  - required
      alias     - optional custom alias (3–30 chars)
      ttl_days  - optional int, days until expiry

    Returns:
      201 { short_url, short_code, long_url, expires_at, created_at }
    """
    data = request.get_json(silent=True) or request.form

    long_url = (data.get("long_url") or "").strip()
    alias = (data.get("alias") or "").strip() or None
    ttl_days_raw = data.get("ttl_days")

    ttl_days = None
    if ttl_days_raw is not None:
        try:
            ttl_days = int(ttl_days_raw)
            if ttl_days < 0:
                return jsonify({"error": "ttl_days must be non-negative."}), 400
        except ValueError:
            return jsonify({"error": "ttl_days must be an integer."}), 400

    try:
        result = services.shorten_url(
            long_url=long_url,
            alias=alias,
            ttl_days=ttl_days,
            client_ip=_get_client_ip(),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    base_url = current_app.config["BASE_URL"]
    code = result["alias"] or result["short_code"]
    result["short_url"] = f"{base_url}/{code}"

    return jsonify(result), 201


# ─── GET /<short_code> ─────────────────────────────────────────────────────────

@api.route("/<short_code>", methods=["GET"])
def redirect_to_url(short_code: str):
    """
    Redirect to the original URL.
    Records a click event asynchronously (same request for simplicity;
    use a task queue like Celery in production).
    """
    record = services.resolve_short_code(short_code)
    if not record:
        abort(404)

    # Record analytics (non-blocking best-effort)
    try:
        repository.record_click(
            url_id=record["id"],
            ip_address=_get_client_ip(),
            user_agent=request.headers.get("User-Agent", ""),
        )
    except Exception:
        pass  # Never fail a redirect due to analytics

    return redirect(record["long_url"], code=301)


# ─── GET /stats/<short_code> ───────────────────────────────────────────────────

@api.route("/stats/<short_code>", methods=["GET"])
def stats(short_code: str):
    """
    Return analytics for a short code.

    Returns:
      200 { short_code, long_url, click_count, recent_clicks, created_at, expires_at }
    """
    data = services.get_stats(short_code)
    if not data:
        return jsonify({"error": "Short code not found."}), 404
    return jsonify(data), 200


# ─── Health Check ──────────────────────────────────────────────────────────────

@api.route("/health", methods=["GET"])
def health():
    """Liveness probe — used by load balancers."""
    return jsonify({"status": "ok"}), 200


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip() -> str:
    """
    Extract real client IP, respecting X-Forwarded-For from reverse proxies.
    In production, configure trusted proxy IPs to prevent spoofing.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def register_routes(app):
    """Register all blueprints with the app."""
    app.register_blueprint(ui)
    app.register_blueprint(api)
