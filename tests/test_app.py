"""
Unit tests for the URL Shortener Service.

Run with:  python -m pytest tests/ -v
"""

import pytest

from app import create_app


@pytest.fixture
def app():
    """Fresh test app with in-memory SQLite for isolation."""
    application = create_app("testing")
    with application.app_context():
        # Clear shared service state before each test
        from app import services
        services._cache.clear()
        services._rate_limiter._counts.clear()
        yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ─── URL Validation Tests ──────────────────────────────────────────────────────

class TestURLValidation:
    def test_valid_http_url(self):
        from app.services import validate_url
        ok, err = validate_url("http://example.com")
        assert ok and not err

    def test_valid_https_url(self):
        from app.services import validate_url
        ok, _ = validate_url("https://www.google.com/search?q=test")
        assert ok

    def test_rejects_javascript_scheme(self):
        from app.services import validate_url
        ok, err = validate_url("javascript:alert(1)")
        assert not ok
        assert "not allowed" in err.lower()

    def test_rejects_data_uri(self):
        from app.services import validate_url
        ok, _ = validate_url("data:text/html,<h1>xss</h1>")
        assert not ok

    def test_rejects_ftp_scheme(self):
        from app.services import validate_url
        ok, err = validate_url("ftp://files.example.com")
        assert not ok
        assert "http" in err.lower()

    def test_rejects_empty_string(self):
        from app.services import validate_url
        ok, _ = validate_url("")
        assert not ok

    def test_rejects_localhost(self):
        from app.services import validate_url
        ok, _ = validate_url("http://localhost/admin")
        assert not ok

    def test_rejects_private_ip(self):
        from app.services import validate_url
        ok, _ = validate_url("http://192.168.1.1/secret")
        assert not ok

    def test_rejects_url_without_domain(self):
        from app.services import validate_url
        ok, _ = validate_url("https://")
        assert not ok


# ─── Base62 Encoding Tests ─────────────────────────────────────────────────────

class TestBase62:
    def test_zero(self):
        from app.services import _base62_encode
        assert _base62_encode(0) == "0"

    def test_known_value(self):
        from app.services import _base62_encode
        # 62 → "10" in Base62
        assert _base62_encode(62) == "10"

    def test_large_number(self):
        from app.services import _base62_encode
        code = _base62_encode(99999999)
        assert len(code) > 0
        assert all(c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" for c in code)

    def test_different_inputs_different_outputs(self):
        from app.services import _base62_encode
        assert _base62_encode(1) != _base62_encode(2)


# ─── Short Code Generation ─────────────────────────────────────────────────────

class TestShortCodeGeneration:
    def test_code_length(self):
        from app.services import _generate_short_code
        code = _generate_short_code("https://example.com", length=7)
        assert len(code) == 7

    def test_deterministic(self):
        from app.services import _generate_short_code
        url = "https://example.com/page"
        assert _generate_short_code(url, 7, 0) == _generate_short_code(url, 7, 0)

    def test_collision_changes_code(self):
        from app.services import _generate_short_code
        url = "https://example.com"
        assert _generate_short_code(url, 7, 0) != _generate_short_code(url, 7, 1)

    def test_only_base62_chars(self):
        from app.services import _generate_short_code
        code = _generate_short_code("https://example.com/test", 7, 0)
        valid = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
        assert all(c in valid for c in code)


# ─── POST /shorten Endpoint ────────────────────────────────────────────────────

class TestShortenEndpoint:
    def test_shorten_valid_url(self, client):
        res = client.post("/shorten", json={"long_url": "https://www.example.com"})
        assert res.status_code == 201
        data = res.get_json()
        assert "short_url" in data
        assert "short_code" in data
        assert data["long_url"] == "https://www.example.com"

    def test_shorten_rejects_invalid_url(self, client):
        res = client.post("/shorten", json={"long_url": "not-a-url"})
        assert res.status_code == 400
        assert "error" in res.get_json()

    def test_shorten_rejects_javascript_url(self, client):
        res = client.post("/shorten", json={"long_url": "javascript:alert(1)"})
        assert res.status_code == 400

    def test_shorten_empty_body(self, client):
        res = client.post("/shorten", json={"long_url": ""})
        assert res.status_code == 400

    def test_deduplication_returns_same_code(self, client):
        url = "https://dedup.example.com/page"
        r1 = client.post("/shorten", json={"long_url": url})
        r2 = client.post("/shorten", json={"long_url": url})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.get_json()["short_code"] == r2.get_json()["short_code"]

    def test_custom_alias(self, client):
        res = client.post("/shorten", json={
            "long_url": "https://alias.example.com",
            "alias": "my-link",
        })
        assert res.status_code == 201
        data = res.get_json()
        assert "my-link" in data["short_url"]

    def test_duplicate_alias_rejected(self, client):
        payload = {"long_url": "https://alias2.example.com", "alias": "taken"}
        client.post("/shorten", json=payload)
        res = client.post("/shorten", json=payload)
        assert res.status_code == 400

    def test_invalid_alias_rejected(self, client):
        res = client.post("/shorten", json={
            "long_url": "https://example.com",
            "alias": "a b",  # space not allowed
        })
        assert res.status_code == 400

    def test_ttl_days_stored(self, client):
        res = client.post("/shorten", json={
            "long_url": "https://expire.example.com",
            "ttl_days": 30,
        })
        assert res.status_code == 201
        assert res.get_json()["expires_at"] is not None

    def test_negative_ttl_rejected(self, client):
        res = client.post("/shorten", json={
            "long_url": "https://example.com",
            "ttl_days": -1,
        })
        assert res.status_code == 400


# ─── GET /<short_code> Redirect ────────────────────────────────────────────────

class TestRedirectEndpoint:
    def _shorten(self, client, url, **kwargs):
        r = client.post("/shorten", json={"long_url": url, **kwargs})
        return r.get_json()

    def test_redirect_to_original(self, client):
        url = "https://redirect.example.com"
        data = self._shorten(client, url)
        code = data["short_code"]
        res = client.get(f"/{code}", follow_redirects=False)
        assert res.status_code == 301
        assert res.headers["Location"] == url

    def test_unknown_code_returns_404(self, client):
        res = client.get("/nonexistent", follow_redirects=False)
        assert res.status_code == 404

    def test_alias_redirects_correctly(self, client):
        url = "https://alias-redirect.example.com"
        self._shorten(client, url, alias="shortcut")
        res = client.get("/shortcut", follow_redirects=False)
        assert res.status_code == 301
        assert res.headers["Location"] == url


# ─── GET /stats/<short_code> ──────────────────────────────────────────────────

class TestStatsEndpoint:
    def test_stats_for_valid_code(self, client):
        r = client.post("/shorten", json={"long_url": "https://stats.example.com"})
        code = r.get_json()["short_code"]

        # Make a click
        client.get(f"/{code}", follow_redirects=False)

        res = client.get(f"/stats/{code}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["click_count"] >= 1
        assert data["long_url"] == "https://stats.example.com"
        assert "recent_clicks" in data

    def test_stats_unknown_code(self, client):
        res = client.get("/stats/doesnotexist")
        assert res.status_code == 404

    def test_stats_click_count_increments(self, client):
        r = client.post("/shorten", json={"long_url": "https://counter.example.com"})
        code = r.get_json()["short_code"]

        for _ in range(3):
            client.get(f"/{code}", follow_redirects=False)

        res = client.get(f"/stats/{code}").get_json()
        assert res["click_count"] == 3


# ─── Health Check ─────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.get_json()["status"] == "ok"
