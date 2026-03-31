# Snip — URL Shortener Service

A production-quality URL shortener built with Python and Flask. It handles the full flow from accepting a long URL, generating a short code, redirecting users, and recording analytics — all in a layered, maintainable architecture that scales from SQLite on a laptop to PostgreSQL behind a load balancer.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Client (Browser)                  │
└─────────────────────────┬───────────────────────────┘
                          │ HTTP
┌─────────────────────────▼───────────────────────────┐
│              Reverse Proxy (nginx / ALB)             │
│           (rate limiting, TLS termination)           │
└──────────┬──────────────────────────────────────────┘
           │             (load balanced)
    ┌──────▼──────┐   ┌──────────────┐   ┌────────────┐
    │  Flask App  │   │  Flask App   │   │  Flask App │
    │  Instance 1 │   │  Instance 2  │   │  Instance N│
    └──────┬──────┘   └──────┬───────┘   └─────┬──────┘
           │                 │                  │
    ┌──────▼─────────────────▼──────────────────▼──────┐
    │          In-Memory Cache (Redis in prod)          │
    └──────────────────────┬───────────────────────────┘
                           │ cache miss
    ┌──────────────────────▼───────────────────────────┐
    │           Database (SQLite / PostgreSQL)          │
    └──────────────────────────────────────────────────┘
```

### Layers

| Layer | File | Responsibility |
|---|---|---|
| Routes / Controllers | `app/routes.py` | Parse HTTP, delegate, return responses |
| Service | `app/services.py` | Business logic: validation, encoding, cache, rate limit |
| Repository | `app/repository.py` | All SQL queries — nothing else |
| Database | `app/database.py` | Connection management, schema, WAL config |
| Config | `app/config.py` | Environment-specific settings |

---

## Getting Started

### Prerequisites

- Python 3.10+

### Setup

```bash
# Clone and enter
git clone https://github.com/your-username/url-shortener.git
cd url-shortener

# Create virtualenv
python -m venv .venv
.venv\Scripts\activate        # Windows
# or: source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure (optional — defaults work out of the box)
cp .env.example .env
# Edit .env as needed

# Run
python run.py
```

Open [http://localhost:5000](http://localhost:5000).

---

## API Reference

### `POST /shorten`

Shorten a long URL.

**Request body (JSON):**
```json
{
  "long_url": "https://www.example.com/very/long/path",
  "alias": "my-link",      // optional: custom alias (3–30 chars)
  "ttl_days": 30           // optional: days until expiry (omit = never)
}
```

**Response `201`:**
```json
{
  "short_url":   "http://localhost:5000/aB3kX2m",
  "short_code":  "aB3kX2m",
  "long_url":    "https://www.example.com/very/long/path",
  "alias":       null,
  "expires_at":  null,
  "created_at":  "2024-01-15T10:30:00+00:00"
}
```

**Error `400`:**
```json
{ "error": "Only http/https URLs are accepted." }
```

---

### `GET /<short_code>`

Redirect to the original URL.

- **301** redirect on success
- **404** if code doesn't exist or URL has expired

```bash
curl -L http://localhost:5000/aB3kX2m
```

---

### `GET /stats/<short_code>`

Fetch analytics for a short code.

**Response `200`:**
```json
{
  "short_code":    "aB3kX2m",
  "long_url":      "https://www.example.com/very/long/path",
  "click_count":   142,
  "created_at":    "2024-01-15T10:30:00",
  "expires_at":    null,
  "recent_clicks": [
    {
      "accessed_at": "2024-01-15T11:00:00",
      "ip_address":  "203.0.113.12",
      "user_agent":  "Mozilla/5.0 ..."
    }
  ]
}
```

---

### `GET /health`

Liveness probe for load balancers.

```json
{ "status": "ok" }
```

---

## Database Schema

```sql
CREATE TABLE urls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    short_code  TEXT    NOT NULL UNIQUE,
    long_url    TEXT    NOT NULL,
    alias       TEXT    UNIQUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME DEFAULT NULL,
    is_active   INTEGER  DEFAULT 1
);

CREATE TABLE analytics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id      INTEGER NOT NULL REFERENCES urls(id) ON DELETE CASCADE,
    accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_address  TEXT,
    user_agent  TEXT
);

-- Indexes
CREATE INDEX idx_urls_short_code  ON urls(short_code);
CREATE INDEX idx_urls_long_url    ON urls(long_url);
CREATE INDEX idx_analytics_url_id ON analytics(url_id);
CREATE INDEX idx_analytics_accessed_at ON analytics(accessed_at);
```

**Index rationale:**
- `idx_urls_short_code` — primary read path on every redirect
- `idx_urls_long_url` — deduplication lookup when shortening
- `idx_analytics_*` — fast aggregation for stats queries

---

## Design Decisions

### Why SHA-256 + Base62 instead of random IDs?

Deterministic generation means the same URL always produces the same candidate code, which enables deduplication without a separate DB lookup on every write. On collision (rare), we hash with an incrementing salt — max 10 retries, which is astronomically unlikely to exhaust.

### Why raw SQL instead of an ORM?

SQLAlchemy adds abstraction worth it at scale, but for this scope it would hide the indexing strategy and make the code harder to reason about. The repository pattern keeps all SQL in one file, so migration to an ORM or PostgreSQL is a single-file change.

### Deduplication

If two users shorten the same URL, they get the same short code. This is opt-in via `DEDUPLICATE_URLS=true` (default). The tradeoff: users can't have separate analytics per "instance" of the same long URL.

### In-memory cache vs. Redis

The `_SimpleCache` class is a thread-safe dict with TTL. It's a drop-in Redis simulation — in production you'd swap it for `redis-py` with zero changes to the service interface. The cache key is `short_code → long_url`, targeting the hottest read path (redirect).

### SSRF Protection

We check `netloc` against private IP ranges and `localhost` before storing a URL. This prevents internal service attacks. For production, use a more complete SSRF library and maintain an allowlist/denylist.

### Rate Limiting

Per-IP token bucket (60-second window) lives in `_RateLimiter`. In production, this must be shared state — move to Redis with a sliding-window counter, or use nginx `limit_req`.

---

## Scaling Strategy

### Short term (single server)

- Enable WAL mode (already on): allows concurrent reads while writing
- Move SQLite file to a fast SSD
- Run with `gunicorn --workers 4` (multiprocessing, not threads)

### Medium term (multiple servers)

- Replace SQLite with PostgreSQL — change `DATABASE_URL`, run same schema
- Replace `_SimpleCache` with Redis — prevents cache inconsistency across instances
- Put nginx in front for SSL termination + `limit_req` rate limiting
- Use a CDN for static assets

### Large scale (millions of requests/day)

- The redirect path (`GET /<code>`) is read-heavy. Cache hit rate > 95% with a warm Redis cluster means DB is rarely touched for redirects.
- Writes (POST /shorten) are far less frequent — primary DB handles them fine with connection pooling (PgBouncer).
- Analytics writes can be moved to a message queue (e.g. Kafka → ClickHouse) to decouple them from the redirect hot path.
- Short code space: 7 Base62 chars = 62^7 ≈ 3.5 trillion unique codes.

```
Redirect path (optimized):
  Browser → CDN (304) → nginx → Flask → Redis (1ms) → 301 redirect
                                           ↓ miss
                                         PostgreSQL → Redis warm → 301
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Expected output: 30+ tests across validation, encoding, API endpoints, and edge cases.

---

## Project Structure

```
url-shortener/
├── app/
│   ├── __init__.py       # App factory
│   ├── config.py         # Environment configs
│   ├── database.py       # DB connection + schema
│   ├── repository.py     # All SQL (repository pattern)
│   ├── services.py       # Business logic
│   └── routes.py         # HTTP layer (Flask blueprints)
├── static/
│   ├── style.css         # UI styles
│   └── app.js            # Frontend logic
├── templates/
│   └── index.html        # Main UI
├── tests/
│   └── test_app.py       # Full test suite
├── .env.example          # Env var template
├── .gitignore
├── requirements.txt
├── run.py                # Entry point
└── README.md
```

---

## Bonus Features Included

| Feature | Details |
|---|---|
| **URL Expiration** | `ttl_days` param stores `expires_at`; resolver checks on every request |
| **Rate Limiting** | Per-IP, 10 req/min default, configurable via `RATE_LIMIT` env var |
| **Custom Aliases** | `alias` param, validated with regex, unique constraint in DB |
| **Deduplication** | Same long URL → same short code (configurable) |
| **SSRF Protection** | Blocks `localhost`, private IPs, non-http/s schemes |
| **Analytics** | Per-click timestamps, IP, user agent |
| **Caching** | Thread-safe in-memory cache with TTL (Redis-ready) |
