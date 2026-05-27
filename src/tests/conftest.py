# tests/conftest.py
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

# Path setup — make src/ importable when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import factories as _factories_module
from services.utils import CircuitState, EmailService

# ---------------------------------------------------------------------------
# JWT secret — mirrors models.py default
# ---------------------------------------------------------------------------
_JWT_SECRET = os.environ.get("HF_JWT_SECRET", "homefinder-jwt-secret-change-in-prod")

@pytest.fixture
def jwt_secret():
    """Return the JWT secret as a fixture for token-related tests."""
    return _JWT_SECRET

# ---------------------------------------------------------------------------
# AUTO-USE FIXTURES (run before/after every test)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_factory_id():
    """Reset PropertyFactory global auto-increment so IDs are deterministic."""
    original = _factories_module._next_id
    _factories_module._next_id = 1
    yield
    _factories_module._next_id = original


@pytest.fixture(autouse=True)
def reset_email_circuit_breaker():
    """Isolate EmailService circuit-breaker state between tests."""
    cb = EmailService._breaker
    cb._failures = 0
    cb._state = CircuitState.CLOSED
    cb._opened_at = None
    yield
    cb._failures = 0
    cb._state = CircuitState.CLOSED
    cb._opened_at = None


# ---------------------------------------------------------------------------
# SHARED FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db_conn():
    """SQLite connection mock.  SELECT id FROM payment returns row [1]."""
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = [1]
    return conn


@pytest.fixture
def patched_get_db(mock_db_conn):
    """Patch payment_service.get_db to yield mock_db_conn for entire test."""
    @contextmanager
    def _fake_db():
        yield mock_db_conn

    with patch("services.payment_service.get_db", _fake_db):
        yield mock_db_conn


@pytest.fixture
def auth_svc():
    """AuthService with ALL repository dependencies replaced by MagicMock."""
    from services.auth_service import AuthService
    svc = AuthService.__new__(AuthService)
    svc._users = MagicMock()
    svc._sessions = MagicMock()
    svc._audit = MagicMock()
    svc._notif = MagicMock()
    svc._pending = MagicMock()
    svc._attempts = MagicMock()
    return svc


@pytest.fixture
def payment_svc(patched_get_db):
    """PaymentService with mocked repos; get_db is already patched."""
    from services.payment_service import PaymentService
    svc = PaymentService.__new__(PaymentService)
    svc._payments = MagicMock()
    svc._props = MagicMock()
    svc._notifs = MagicMock()
    svc._audit = MagicMock()
    svc._props.find_by_id.return_value = {
        "id": 1,
        "title": "Ocean View Villa",
        "price": 250_000.0,
        "category": "residential",
        "is_available": 1,
    }
    return svc