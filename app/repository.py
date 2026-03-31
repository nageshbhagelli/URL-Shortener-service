"""
Repository layer — all SQL lives here, nowhere else.

Each method is a thin wrapper around SQL; zero business logic.
To migrate to PostgreSQL: swap the get_db() import and change ? → %s.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from .database import get_db


# ─── URL Repository ────────────────────────────────────────────────────────────

def find_url_by_short_code(short_code: str) -> Optional[Dict]:
    """Primary read path — called on every redirect."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM urls WHERE short_code = ? AND is_active = 1",
        (short_code,)
    ).fetchone()
    return dict(row) if row else None


def find_url_by_alias(alias: str) -> Optional[Dict]:
    db = get_db()
    row = db.execute(
        "SELECT * FROM urls WHERE alias = ? AND is_active = 1",
        (alias,)
    ).fetchone()
    return dict(row) if row else None


def find_url_by_long_url(long_url: str) -> Optional[Dict]:
    """Used for deduplication — returns existing record if URL was already shortened."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM urls WHERE long_url = ? AND is_active = 1",
        (long_url,)
    ).fetchone()
    return dict(row) if row else None


def insert_url(short_code: str, long_url: str,
               alias: Optional[str] = None,
               expires_at: Optional[datetime] = None) -> int:
    """Insert a new URL mapping; returns the new row id."""
    db = get_db()
    cursor = db.execute(
        """INSERT INTO urls (short_code, long_url, alias, expires_at)
           VALUES (?, ?, ?, ?)""",
        (short_code, long_url, alias,
         expires_at.isoformat() if expires_at else None)
    )
    db.commit()
    return cursor.lastrowid


def short_code_exists(short_code: str) -> bool:
    """Collision check — needed during Base62 code generation."""
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM urls WHERE short_code = ?", (short_code,)
    ).fetchone()
    return row is not None


# ─── Analytics Repository ──────────────────────────────────────────────────────

def record_click(url_id: int, ip_address: str, user_agent: str):
    """Append a click event. Fire-and-forget in the redirect path."""
    db = get_db()
    db.execute(
        """INSERT INTO analytics (url_id, ip_address, user_agent)
           VALUES (?, ?, ?)""",
        (url_id, ip_address, user_agent)
    )
    db.commit()


def get_click_count(url_id: int) -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM analytics WHERE url_id = ?", (url_id,)
    ).fetchone()
    return row["cnt"] if row else 0


def get_recent_clicks(url_id: int, limit: int = 10) -> List[Dict]:
    db = get_db()
    rows = db.execute(
        """SELECT accessed_at, ip_address, user_agent
           FROM analytics
           WHERE url_id = ?
           ORDER BY accessed_at DESC
           LIMIT ?""",
        (url_id, limit)
    ).fetchall()
    return [dict(r) for r in rows]
