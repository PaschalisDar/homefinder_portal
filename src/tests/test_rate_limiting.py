# tests/test_rate_limiting.py
import pytest
from unittest.mock import patch
from repositories.auth_utils import LoginAttemptRepository
from services.exceptions import RateLimitExceeded


class TestRateLimiting:
    """Verify that ≥3 failed attempts within the 5-minute window block logins."""

    def test_rate_limited_flag_raises_rate_limit_exceeded(self, auth_svc):
        """is_rate_limited=True ⟹ initiate_login raises RateLimitExceeded."""
        auth_svc._attempts.is_rate_limited.return_value = True

        with pytest.raises(RateLimitExceeded, match="Too many login attempts"):
            auth_svc.initiate_login("alice", "wrong_password", ip="10.0.0.1")

    def test_rate_limit_writes_audit_entry(self, auth_svc):
        """Blocked login attempt must be recorded in the audit log."""
        auth_svc._attempts.is_rate_limited.return_value = True

        with pytest.raises(RateLimitExceeded):
            auth_svc.initiate_login("alice", "x", ip="10.0.0.1")

        auth_svc._audit.log.assert_called_once_with(
            "login_rate_limited",
            detail="user=alice",
            ip_address="10.0.0.1",
        )

    def test_below_threshold_allows_login_to_proceed(self, auth_svc):
        """is_rate_limited=False ⟹ no RateLimitExceeded; login flow continues."""
        auth_svc._attempts.is_rate_limited.return_value = False
        auth_svc._users.find_by_username.return_value = None  # unknown user

        result = auth_svc.initiate_login("bob", "pass", ip="10.0.0.1")

        assert result["ok"] is False
        assert "credentials" in result["error"].lower()

    def test_login_attempt_repo_threshold_boundary(self):
        """
        Unit-test LoginAttemptRepository.is_rate_limited() directly.
        COUNT = 2  ⟹ not limited (< 3)
        COUNT = 3  ⟹ limited    (≥ 3)
        """
        from repositories.auth_utils import LoginAttemptRepository
        repo = LoginAttemptRepository.__new__(LoginAttemptRepository)

        with patch.object(repo, "_q") as mock_q:
            mock_q.return_value = 2
            assert repo.is_rate_limited("alice") is False

            mock_q.return_value = 3
            assert repo.is_rate_limited("alice") is True

            mock_q.return_value = 10
            assert repo.is_rate_limited("alice") is True

    def test_failed_credential_records_attempt(self, auth_svc):
        """Bad password ⟹ _attempts.record() is called."""
        auth_svc._attempts.is_rate_limited.return_value = False
        auth_svc._users.find_by_username.return_value = {
            "id": 1, "username": "alice", "is_active": 1,
            "password_hash": "not_a_real_hash",
        }

        with patch("services.auth_service.verify_password", return_value=False):
            auth_svc.initiate_login("alice", "wrong", ip="10.0.0.1")

        auth_svc._attempts.record.assert_called_once_with("alice", "10.0.0.1")