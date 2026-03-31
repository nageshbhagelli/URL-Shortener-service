"""
Database layer - handles connection and schema initialization.

Built on raw sqlite3 for SQLite (dev) but the schema SQL is standard enough
to run on PostgreSQL with zero changes (swap ? → %s for psycopg2 if needed,
or just use SQLAlchemy for the production abstraction).
"""

import sqlite3
import os
from flask import Flask, g

# Holds a single persistent connection for :memory: databases (testing).
# Each call to sqlite3.connect(":memory:") spawns a fresh, empty database,
# so we keep one alive for the lifetime of the app in test mode.
_memory_conn: sqlite3.Connection = None


def _get_db_path(app: Flask) -> str:
    """Extract the file path from a sqlite:/// DATABASE_URL."""
    url = app.config["DATABASE_URL"]
    if url == "sqlite:///:memory:":
        return ":memory:"
    # e.g. sqlite:///urls.db → urls.db (relative to instance)
    return url.replace("sqlite:///", "")


def _make_connection(db_path: str) -> sqlite3.Connection:
    """Open (or reuse) a SQLite connection."""
    global _memory_conn
    if db_path == ":memory:":
        # Reuse the single shared in-memory connection.
        if _memory_conn is None:
            _memory_conn = sqlite3.connect(
                db_path,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            _memory_conn.row_factory = sqlite3.Row
            _memory_conn.execute("PRAGMA foreign_keys=ON")
        return _memory_conn

    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Better concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db(app: Flask = None):
    """
    Return a per-request database connection stored on Flask's 'g' object.
    For :memory: SQLite (testing) all requests share the same connection.
    """
    from flask import current_app

    target_app = app or current_app
    if "db" not in g:
        db_path = _get_db_path(target_app)
        g.db = _make_connection(db_path)
    return g.db


def close_db(error=None):
    """
    Close DB connection at end of request.
    For :memory: databases we keep the connection alive across requests.
    """
    db = g.pop("db", None)
    if db is not None and db is not _memory_conn:
        db.close()


# ─── Schema ────────────────────────────────────────────────────────────────────
# This schema is intentionally PostgreSQL-compatible:
#   - Use SERIAL / BIGSERIAL instead of INTEGER PRIMARY KEY AUTOINCREMENT in PG
#   - TEXT works in both
#   - TIMESTAMP WITHOUT TIME ZONE in PG instead of DATETIME
#   - Indexes are identical

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS urls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    short_code  TEXT    NOT NULL UNIQUE,
    long_url    TEXT    NOT NULL,
    alias       TEXT    UNIQUE,                  -- custom alias (optional)
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME DEFAULT NULL,           -- NULL = never expires
    is_active   INTEGER  DEFAULT 1               -- soft-delete / disable
);

-- Fast lookup on short_code (most frequent query path)
CREATE INDEX IF NOT EXISTS idx_urls_short_code ON urls(short_code);

-- Deduplication: find existing entry for a given long_url
CREATE INDEX IF NOT EXISTS idx_urls_long_url   ON urls(long_url);

CREATE TABLE IF NOT EXISTS analytics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id      INTEGER NOT NULL REFERENCES urls(id) ON DELETE CASCADE,
    accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ip_address  TEXT,
    user_agent  TEXT
);

-- Fast aggregation queries for stats
CREATE INDEX IF NOT EXISTS idx_analytics_url_id     ON analytics(url_id);
CREATE INDEX IF NOT EXISTS idx_analytics_accessed_at ON analytics(accessed_at);
"""


def init_db(app: Flask):
    """Create tables on startup and register the teardown hook."""
    global _memory_conn
    app.teardown_appcontext(close_db)

    db_path = _get_db_path(app)

    if db_path == ":memory:":
        # Reset any leftover state from a previous test session.
        _memory_conn = None

    # Ensure parent directory exists for file-based DBs.
    if db_path != ":memory:" and not os.path.isabs(db_path):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # Bootstrap: create tables using a fresh standalone connection.
    # For :memory: this also initialises _memory_conn via _make_connection.
    conn = _make_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    if db_path != ":memory:":
        conn.close()
