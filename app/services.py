"""
Service layer — business logic lives here.

Routes call services; services call repositories.
Services know nothing about HTTP (no request/response objects).
"""

import hashlib
import re
import string
import time
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Optional, Dict, Tuple
from urllib.parse import urlparse

from flask import current_app

from . import repository

# ─── Base62 Encoding ───────────────────────────────────────────────────────────

_BASE62_CHARS = string.digits + string.ascii_letters  # 0-9A-Za-z


def _base62_encode(num: int) -> str:
    """Convert a positive integer to a Base62 string."""
    if num == 0:
        return _BASE62_CHARS[0]
    result = []
    while num:
        result.append(_BASE62_CHARS[num % 62])
        num //= 62
    return "".join(reversed(result))


def _generate_short_code(long_url: str, length: int = 7, attempt: int = 0) -> str:
    """
    Deterministic short code generation via SHA-256 of the URL.
    On collision (attempt > 0) we salt with the attempt counter,
    making collision resolution O(1) extra hash — not a UUID spin loop.
    """
    salt = str(attempt).encode() if attempt else b""
    digest = hashlib.sha256(long_url.encode() + salt).hexdigest()
    # Convert hex → integer → Base62
    num = int(digest[:16], 16)  # Use first 64 bits for speed
    code = _base62_encode(num)
    return code[:length]


# ─── URL Validation ────────────────────────────────────────────────────────────

# Allowlist of safe schemes
_SAFE_SCHEMES = {"http", "https"}

# Block obviously malicious patterns (javascript:, data:, file:, etc.)
_BLOCKED_SCHEME_RE = re.compile(
    r"^(javascript|data|file|vbscript|about):", re.IGNORECASE
)


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Checks scheme, netloc, and blocks known-malicious patterns.
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string."

    # Strip whitespace — common paste artifact
    url = url.strip()

    if _BLOCKED_SCHEME_RE.match(url):
        return False, "URL scheme is not allowed."

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL could not be parsed."

    if parsed.scheme not in _SAFE_SCHEMES:
        return False, f"Only http/https URLs are accepted. Got: '{parsed.scheme}'."

    if not parsed.netloc:
        return False, "URL has no domain."

    # Reject bare IPs with private ranges (basic SSRF mitigation)
    # In production, use a proper SSRF blocklist library
    netloc_lower = parsed.netloc.lower()
    ssrf_patterns = ["localhost", "127.", "0.0.0.0", "169.254.", "::1", "10.", "192.168."]
    if any(netloc_lower.startswith(p) or netloc_lower == p.rstrip(".") for p in ssrf_patterns):
        return False, "Internal/private addresses are not allowed."

    return True, ""


# ─── In-Memory Cache (Redis simulation) ────────────────────────────────────────

class _SimpleCache:
    """
    Thread-safe in-memory LRU-ish cache.
    In production: replace with Redis (redis-py) — same interface.
    Key insight: the redirect path is read-heavy; caching short_code→long_url
    eliminates most DB hits at scale.
    """

    def __init__(self):
        self._store: Dict[str, Tuple[any, float]] = {}
        self._lock = Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            value, expires = entry
            if expires and time.time() > expires:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value, ttl_seconds: int = 300):
        with self._lock:
            self._store[key] = (value, time.time() + ttl_seconds)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()


_cache = _SimpleCache()


# ─── Rate Limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    """
    Token-bucket style rate limiter keyed by IP.
    In production: use Redis + sliding-window counters.
    """

    def __init__(self):
        self._counts: Dict[str, Tuple[int, float]] = {}
        self._lock = Lock()

    def is_allowed(self, ip: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.time()
        with self._lock:
            count, window_start = self._counts.get(ip, (0, now))
            if now - window_start > window_seconds:
                # New window
                self._counts[ip] = (1, now)
                return True
            if count >= limit:
                return False
            self._counts[ip] = (count + 1, window_start)
            return True


_rate_limiter = _RateLimiter()


# ─── URL Shortening Service ────────────────────────────────────────────────────

def shorten_url(long_url: str,
                alias: Optional[str] = None,
                ttl_days: Optional[int] = None,
                client_ip: str = "unknown") -> Dict:
    """
    Core shortening logic:
    1. Rate limit check
    2. Validate URL
    3. Deduplication (if enabled)
    4. Generate collision-free short code
    5. Persist and cache
    """
    rate_limit = current_app.config["RATE_LIMIT"]
    if not _rate_limiter.is_allowed(client_ip, rate_limit):
        raise ValueError(f"Rate limit exceeded. Max {rate_limit} requests/minute.")

    is_valid, err = validate_url(long_url)
    if not is_valid:
        raise ValueError(err)

    # Normalize URL (remove trailing slash inconsistencies)
    long_url = long_url.strip().rstrip("/") if long_url.endswith("/") and len(long_url) > 8 else long_url.strip()

    # Handle custom alias
    if alias:
        alias = alias.strip()
        if not re.match(r'^[A-Za-z0-9_-]{3,30}$', alias):
            raise ValueError("Alias must be 3–30 chars, alphanumeric, hyphens, or underscores.")
        existing = repository.find_url_by_alias(alias)
        if existing:
            raise ValueError(f"Alias '{alias}' is already taken.")

    # Deduplication — same long URL returns same short code
    if current_app.config.get("DEDUPLICATE_URLS") and not alias:
        existing = repository.find_url_by_long_url(long_url)
        if existing:
            return _format_url_record(existing)

    # Generate unique short code with collision retry
    code_length = current_app.config["SHORT_CODE_LENGTH"]
    short_code = None
    for attempt in range(10):  # 10 attempts before giving up (astronomically unlikely)
        candidate = _generate_short_code(long_url, code_length, attempt)
        if not repository.short_code_exists(candidate):
            short_code = candidate
            break

    if not short_code:
        raise RuntimeError("Failed to generate a unique short code after 10 attempts.")

    # Calculate expiry
    expires_at = None
    effective_ttl = ttl_days if ttl_days is not None else current_app.config["DEFAULT_TTL_DAYS"]
    if effective_ttl and effective_ttl > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=effective_ttl)

    url_id = repository.insert_url(short_code, long_url, alias, expires_at)

    record = {
        "id": url_id,
        "short_code": alias or short_code,
        "long_url": long_url,
        "alias": alias,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Cache the mapping
    cache_ttl = current_app.config["CACHE_TTL_SECONDS"]
    _cache.set(alias or short_code, long_url, cache_ttl)

    return record


def resolve_short_code(short_code: str) -> Optional[Dict]:
    """
    Resolve a short code to its long URL.
    Checks cache first, falls back to DB.
    Returns None if not found or expired.
    """
    # Cache hit
    cached_url = _cache.get(short_code)
    if cached_url:
        # Still need the DB record for analytics + expiry check
        record = repository.find_url_by_short_code(short_code)
        if not record:
            record = repository.find_url_by_alias(short_code)
        if record:
            return dict(record)
        # Cache stale — clear it
        _cache.delete(short_code)
        return None

    # Cache miss — hit DB
    record = repository.find_url_by_short_code(short_code)
    if not record:
        record = repository.find_url_by_alias(short_code)
    if not record:
        return None

    # Expiry check
    if record.get("expires_at"):
        exp = datetime.fromisoformat(str(record["expires_at"]))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            return None  # Expired

    # Warm the cache
    cache_ttl = current_app.config["CACHE_TTL_SECONDS"]
    _cache.set(short_code, record["long_url"], cache_ttl)

    return dict(record)


def get_stats(short_code: str) -> Optional[Dict]:
    """Return click analytics for a short code."""
    record = repository.find_url_by_short_code(short_code)
    if not record:
        record = repository.find_url_by_alias(short_code)
    if not record:
        return None

    click_count = repository.get_click_count(record["id"])
    recent = repository.get_recent_clicks(record["id"], limit=10)

    return {
        "short_code": short_code,
        "long_url": record["long_url"],
        "created_at": record["created_at"],
        "expires_at": record["expires_at"],
        "click_count": click_count,
        "recent_clicks": recent,
    }


def _format_url_record(record: Dict) -> Dict:
    """Normalize a DB row dict to API response format."""
    return {
        "id": record["id"],
        "short_code": record["alias"] or record["short_code"],
        "long_url": record["long_url"],
        "alias": record.get("alias"),
        "expires_at": record.get("expires_at"),
        "created_at": record.get("created_at"),
    }
