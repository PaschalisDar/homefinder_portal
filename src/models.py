"""
models.py — HomeFinder Portal
Database schema (SQLite), PII encryption (AES-256-GCM), and password hashing (PBKDF2-SHA256).

References:
- SDS Section 2.1: Data Model (ERD) & Table 1 (Entity-to-Requirement Traceability Matrix).
- SDS Section 2.2: Authentication & Security Flow.
- SRS NFR-03: GDPR compliance (encryption at rest).
- SRS NFR-04: Reliability/Auditability.
"""

import os
import sqlite3
import hashlib
import hmac
import base64
from contextlib import contextmanager
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------------------
# Configuration & Environment
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent / "data" / "homefinder.db"

# 32-byte AES key derived from environment variable (SRS NFR-03: GDPR secure storage).
_RAW_SECRET = os.environ.get("HF_SECRET_KEY", "homefinder-dev-secret-change-in-prod")
_AES_KEY: bytes = hashlib.sha256(_RAW_SECRET.encode()).digest()  # 256-bit

# HS256 JWT signing secret
JWT_SECRET: str = os.environ.get("HF_JWT_SECRET", "homefinder-jwt-secret-change-in-prod")

# Maintenance mode flag (SRS NFR-05 / RE-15: Weekly 30-min window).
MAINTENANCE_MODE: bool = os.environ.get("HF_MAINTENANCE", "0") == "1"

# ---------------------------------------------------------------------------
# AES-256-GCM PII Encryption (SDS Section 2.1 / SRS NFR-03)
# ---------------------------------------------------------------------------

def encrypt_pii(plaintext: str) -> str:
    """Encrypt a PII string; returns base64(nonce[12] || ciphertext+tag)."""
    aesgcm = AESGCM(_AES_KEY)
    nonce  = os.urandom(12)
    ct     = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_pii(token: str) -> str:
    """Decrypt a base64-encoded AES-256-GCM blob back to plaintext."""
    raw    = base64.b64decode(token)
    nonce  = raw[:12]
    ct     = raw[12:]
    aesgcm = AESGCM(_AES_KEY)
    return aesgcm.decrypt(nonce, ct, None).decode()


def hash_pii(plaintext: str) -> str:
    """Deterministic HMAC-SHA256 of a PII string for indexed equality lookups.

    Keyed with _AES_KEY so a leaked database without the app key cannot be
    reversed via rainbow tables. Lowercased before hashing for case-insensitive
    email matching.
    """
    return hmac.new(_AES_KEY, plaintext.lower().encode(), hashlib.sha256).hexdigest()

# ---------------------------------------------------------------------------
# Password Hashing (SDS Section 2.1)
# Uses PBKDF2-SHA256 at 260,000 iterations to satisfy secure storage requirements.
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a salted PBKDF2-SHA256 hash as a storable string."""
    salt = os.urandom(32)
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + dk).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time comparison for password verification."""
    raw  = base64.b64decode(stored_hash)
    salt = raw[:32]
    dk   = raw[32:]
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return hmac.compare_digest(candidate, dk)

# ---------------------------------------------------------------------------
# Database Connection & Concurrency (SDS Section 1)
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    """Yield an auto-commit/rollback sqlite3 connection (Enforces WAL mode/FKs)."""
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a plain dict (returns {} for None)."""
    return dict(row) if row else {}

# ---------------------------------------------------------------------------
# Schema DDL (SDS Section 2.1: Data Model ERD & Table 1)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- USER (SRS FR-01, FR-02, NFR-03)
CREATE TABLE IF NOT EXISTS user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user'
                          CHECK(role IN ('user','admin','supervisor')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    totp_secret   TEXT,
    created_at    DATETIME DEFAULT (datetime('now'))
);

-- USER_PROFILE: PII columns encrypted at rest (SRS NFR-03)
CREATE TABLE IF NOT EXISTS user_profile (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL UNIQUE REFERENCES user(id) ON DELETE CASCADE,
    email_enc    TEXT    NOT NULL,
    email_hash   TEXT    UNIQUE,
    phone_enc    TEXT,
    full_name    TEXT,
    gdpr_consent INTEGER NOT NULL DEFAULT 0 CHECK(gdpr_consent IN (0,1)),
    consent_date DATETIME
);

-- PROPERTY (SRS FR-03, FR-04, FR-10)
CREATE TABLE IF NOT EXISTS property (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    description  TEXT,
    price        REAL    NOT NULL CHECK(price >= 0),
    location     TEXT    NOT NULL,
    category     TEXT    NOT NULL CHECK(category IN ('residential','commercial','rental')),
    bedrooms     INTEGER,
    bathrooms    INTEGER,
    area_sqm     REAL,
    is_available INTEGER NOT NULL DEFAULT 1,
    sold_at      DATETIME,
    has_garden    INTEGER NOT NULL DEFAULT 0 CHECK(has_garden IN (0,1)),
    has_parking   INTEGER NOT NULL DEFAULT 0 CHECK(has_parking IN (0,1)),
    office_spaces INTEGER,                              -- CommercialProperty classification
    lease_duration_months INTEGER,
    security_deposit      REAL,
    owner_id     INTEGER REFERENCES user(id),
    created_at   DATETIME DEFAULT (datetime('now')),
    updated_at   DATETIME DEFAULT (datetime('now'))
);

-- PROPERTY_IMAGE
CREATE TABLE IF NOT EXISTS property_image (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id   INTEGER NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    image_path    TEXT    NOT NULL,
    display_order INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_property_price    ON property(price);
CREATE INDEX IF NOT EXISTS idx_property_location ON property(location);
CREATE INDEX IF NOT EXISTS idx_property_category ON property(category);

-- PAYMENT: ACID compliance (SDS Section 2.3, SRS FR-11, NFR-03)
CREATE TABLE IF NOT EXISTS payment (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES user(id),
    property_id    INTEGER NOT NULL REFERENCES property(id),
    amount         REAL    NOT NULL CHECK(amount > 0),
    status         TEXT    NOT NULL DEFAULT 'pending'
                           CHECK(status IN ('pending','completed','failed','refunded')),
    payment_method TEXT    NOT NULL DEFAULT 'credit_card',
    reference      TEXT    NOT NULL UNIQUE,
    created_at     DATETIME DEFAULT (datetime('now'))
);

-- AUDIT_LOG: 3-month retention (SDS Section 2.1, SRS NFR-04, RE-14)
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES user(id),
    action     TEXT    NOT NULL,
    detail     TEXT,
    ip_address TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- API_SESSION: Single-session enforcement (SDS Section 2.2.4, SRS NFR-02)
CREATE TABLE IF NOT EXISTS api_session (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL,
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now')),
    expires_at DATETIME
);

-- PENDING_2FA: Short-lived TOTP token hash with 5-min expiry (SDS Section 2.2.3, SRS NFR-01)
CREATE TABLE IF NOT EXISTS pending_2fa (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    token_hash TEXT    NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT (datetime('now')),
    used       INTEGER NOT NULL DEFAULT 0 CHECK(used IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_pending_2fa_user ON pending_2fa(user_id);

-- LOGIN_ATTEMPT: Rate-limit tracking (SDS Section 2.2.1, SRS NFR-02)
CREATE TABLE IF NOT EXISTS login_attempt (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT    NOT NULL,
    ip_address TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_attempt_user ON login_attempt(username, created_at);

-- FAVORITE (SRS FR-05)
CREATE TABLE IF NOT EXISTS favorite (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    property_id INTEGER NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    created_at  DATETIME DEFAULT (datetime('now')),
    UNIQUE(user_id, property_id)
);

-- APPOINTMENT (SRS FR-06)
CREATE TABLE IF NOT EXISTS appointment (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES user(id),
    property_id  INTEGER NOT NULL REFERENCES property(id),
    scheduled_at DATETIME NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                      CHECK(status IN ('pending','confirmed','cancelled')),
    notes        TEXT,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   DATETIME DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_appointment 
ON appointment(property_id, scheduled_at) WHERE status != 'cancelled';

-- INQUIRY (SRS FR-07)
CREATE TABLE IF NOT EXISTS inquiry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id),
    property_id INTEGER NOT NULL REFERENCES property(id),
    message     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','responded','closed')),
    response    TEXT,
    created_at  DATETIME DEFAULT (datetime('now'))
);

-- NOTIFICATION (SRS FR-08, FR-10)
CREATE TABLE IF NOT EXISTS notification (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    title      TEXT    NOT NULL,
    message    TEXT    NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- PRICE_ALERT (SRS FR-07)
CREATE TABLE IF NOT EXISTS price_alert (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    property_id INTEGER NOT NULL REFERENCES property(id) ON DELETE CASCADE,
    threshold   REAL    NOT NULL,
    created_at  DATETIME DEFAULT (datetime('now')),
    UNIQUE(user_id, property_id)
);

-- SESSION (For managing log-ins/log-outs)
CREATE TABLE IF NOT EXISTS user_session (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    session_token TEXT NOT NULL,
    expires_at    DATETIME NOT NULL,
    created_at    DATETIME DEFAULT (datetime('now'))
);
"""


def init_db():
    """Create all tables and execute necessary migrations."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
        # Migration: add display_order to property_image if missing
        cols = {row[1] for row in conn.execute("PRAGMA table_info(property_image)")}
        if "display_order" not in cols:
            conn.execute("ALTER TABLE property_image ADD COLUMN display_order INTEGER DEFAULT 0")
        # Migration: add sold_at to property if missing
        prop_cols = {row[1] for row in conn.execute("PRAGMA table_info(property)")}
        if "sold_at" not in prop_cols:
            conn.execute("ALTER TABLE property ADD COLUMN sold_at DATETIME")
        # Migration: add email_hash to user_profile for deterministic lookup
        profile_cols = {row[1] for row in conn.execute("PRAGMA table_info(user_profile)")}
        if "email_hash" not in profile_cols:
            conn.execute("ALTER TABLE user_profile ADD COLUMN email_hash TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profile_email_hash ON user_profile(email_hash)")
    print("[DB] Schema initialised.")