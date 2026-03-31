"""
Configuration classes for different environments.
Swap DATABASE_URL env var to point to PostgreSQL in production.
"""

import os


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    # SQLite by default; set DATABASE_URL=postgresql://... for Postgres
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///urls.db")

    # Short code length (Base62 chars)
    SHORT_CODE_LENGTH = int(os.getenv("SHORT_CODE_LENGTH", "7"))

    # URL time-to-live in days (0 = no expiry)
    DEFAULT_TTL_DAYS = int(os.getenv("DEFAULT_TTL_DAYS", "0"))

    # Rate limiting: max requests per IP per minute
    RATE_LIMIT = int(os.getenv("RATE_LIMIT", "10"))

    # In-memory cache TTL in seconds
    CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

    # Enable duplicate URL deduplication (same long URL → same short code)
    DEDUPLICATE_URLS = os.getenv("DEDUPLICATE_URLS", "true").lower() == "true"


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    # In production, DATABASE_URL must be set externally (e.g., PostgreSQL)


class TestingConfig(BaseConfig):
    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"
    RATE_LIMIT = 1000  # Disable effective rate limiting during tests
    DEDUPLICATE_URLS = True


_config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str = "development"):
    return _config_map.get(name, DevelopmentConfig)
