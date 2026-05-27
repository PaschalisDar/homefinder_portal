# tests/test_auth_token_management.py
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
import jwt


class TestAuthServiceTokenManagement:
    """Validate 2FA pre-auth JWT lifecycle: expiry, phase, leeway, success."""

    def _pre_auth_token(self, jwt_secret, exp_delta: timedelta,
                        phase: str = "pre_auth", sub: str = "7") -> str:
        return jwt.encode(
            {"sub": sub, "phase": phase,
             "exp": datetime.now(timezone.utc) + exp_delta},
            jwt_secret, algorithm="HS256",
        )

    def test_expired_pre_auth_token_is_rejected(self, auth_svc, jwt_secret):
        """Token expired 200 s ago (outside 10 s leeway) ⟹ error."""
        token = self._pre_auth_token(jwt_secret, timedelta(seconds=-200))
        result = auth_svc.verify_2fa(token, "123456")

        assert result["ok"] is False
        assert "expired" in result["error"].lower()

    def test_wrong_phase_token_is_rejected(self, auth_svc, jwt_secret):
        """Token with phase='access' (not 'pre_auth') ⟹ phase error."""
        token = self._pre_auth_token(jwt_secret, timedelta(hours=1), phase="access")
        result = auth_svc.verify_2fa(token, "123456")

        assert result["ok"] is False
        assert "phase" in result["error"].lower()

    def test_token_within_leeway_is_accepted(self, auth_svc, jwt_secret):
        """Token expired 5 s ago (within 10 s leeway) ⟹ NOT rejected as expired."""
        token = self._pre_auth_token(jwt_secret, timedelta(seconds=-5))
        auth_svc._users.find_by_id.return_value = {
            "id": 7, "username": "carol", "role": "user",
            "totp_secret": "AAAA", "is_active": 1,
        }
        auth_svc._pending.verify_and_consume.return_value = False
        with patch("services.auth_service.verify_totp_token", return_value=False):
            result = auth_svc.verify_2fa(token, "000000")

        # JWT leeway accepted the token — failure is TOTP, not JWT expiry
        assert "Session expired" not in result.get("error", "")

    def test_successful_2fa_returns_access_token_with_correct_claims(
        self, auth_svc, jwt_secret
    ):
        """Complete 2FA flow ⟹ access_token is a valid HS256 JWT with role claim."""
        token = self._pre_auth_token(jwt_secret, timedelta(seconds=60))
        auth_svc._users.find_by_id.return_value = {
            "id": 7, "username": "admin_user", "role": "admin",
            "totp_secret": "BBBB", "is_active": 1,
        }
        auth_svc._pending.verify_and_consume.return_value = True
        auth_svc._sessions.create.return_value = None

        result = auth_svc.verify_2fa(token, "123456")

        assert result["ok"] is True
        assert result["role"] == "admin"
        assert result["username"] == "admin_user"

        decoded = jwt.decode(result["access_token"], jwt_secret, algorithms=["HS256"])
        assert decoded["sub"] == "7"
        assert decoded["role"] == "admin"

    def test_access_token_ttl_is_24_hours(self, auth_svc, jwt_secret):
        """Generated access token must expire in ≈24 h (±60 s tolerance)."""
        token = self._pre_auth_token(jwt_secret, timedelta(seconds=60))
        auth_svc._users.find_by_id.return_value = {
            "id": 7, "username": "user7", "role": "user",
            "totp_secret": "CCCC", "is_active": 1,
        }
        auth_svc._pending.verify_and_consume.return_value = True
        auth_svc._sessions.create.return_value = None

        result = auth_svc.verify_2fa(token, "123456")
        decoded = jwt.decode(result["access_token"], jwt_secret, algorithms=["HS256"])

        expected_exp = datetime.now(timezone.utc) + timedelta(hours=24)
        actual_exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        assert abs((actual_exp - expected_exp).total_seconds()) < 60

    def test_invalid_jwt_signature_is_rejected(self, auth_svc):
        """Token signed with a wrong secret ⟹ InvalidTokenError ⟹ error."""
        bad_token = jwt.encode(
            {"sub": "1", "phase": "pre_auth",
             "exp": datetime.now(timezone.utc) + timedelta(seconds=60)},
            "totally-wrong-secret-that-is-long-enough", algorithm="HS256",
        )
        result = auth_svc.verify_2fa(bad_token, "123456")
        assert result["ok"] is False