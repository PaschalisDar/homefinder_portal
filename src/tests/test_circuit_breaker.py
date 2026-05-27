# tests/test_circuit_breaker.py
import time
from unittest.mock import patch, MagicMock
import pytest
from services.utils import CircuitBreaker, CircuitState, EmailService
from services.notification_service import NotificationService


class TestNotificationCircuitBreaker:
    """
    Verify CircuitBreaker state machine: CLOSED → OPEN after 3 failures,
    fast-fail behaviour while OPEN, and HALF_OPEN recovery probe.
    """

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(failure_threshold=3, name="CB_Init")
        assert cb.state == CircuitState.CLOSED

    def test_single_failure_leaves_circuit_closed(self):
        cb = CircuitBreaker(failure_threshold=3, name="CB_Single")
        with pytest.raises(ConnectionError):
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("once")))
        assert cb.state == CircuitState.CLOSED

    def test_two_failures_leave_circuit_closed(self):
        cb = CircuitBreaker(failure_threshold=3, name="CB_Two")

        def smtp_fail():
            raise ConnectionError("SMTP down")

        for _ in range(2):
            with pytest.raises(ConnectionError):
                cb.call(smtp_fail)
        assert cb.state == CircuitState.CLOSED

    def test_circuit_opens_after_exactly_3_consecutive_failures(self):
        """3 consecutive SMTP failures ⟹ circuit transitions to OPEN."""
        cb = CircuitBreaker(failure_threshold=3, name="CB_Open")

        def smtp_fail():
            raise ConnectionError("SMTP connection refused")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(smtp_fail)
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_fast_fails_without_invoking_function(self):
        """Once OPEN, the wrapped function must NOT be called — fail fast."""
        cb = CircuitBreaker(failure_threshold=3, name="CB_FastFail")
        tracker = MagicMock(side_effect=ConnectionError("SMTP down"))

        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(tracker)

        assert cb.state == CircuitState.OPEN

        # 4th attempt: must raise RuntimeError WITHOUT calling tracker again
        with pytest.raises(RuntimeError, match="Circuit OPEN"):
            cb.call(tracker)

        assert tracker.call_count == 3     # only the 3 real attempts

    def test_email_service_returns_false_when_circuit_is_open(self):
        """EmailService.send() must return False (not raise) when OPEN."""
        breaker = EmailService._breaker
        breaker._failures = 3
        breaker._state = CircuitState.OPEN
        breaker._opened_at = time.time()

        result = EmailService.send("user@homefinder.gr", "Test", "Body")
        assert result is False

    def test_notification_service_logs_circuit_open_and_routes_to_fallback(self):
        """
        When EmailService is unavailable (circuit OPEN), NotificationService
        must log a warning that references the circuit state, signalling that
        token dispatch has been routed to the SMS fallback channel.
        """
        with patch(
            "services.notification_service.NotificationRepository"
        ), patch(
            "services.notification_service.UserRepository"
        ):
            svc = NotificationService()

        with patch(
            "services.notification_service.EmailService"
        ) as MockEmail, patch(
            "services.notification_service.logger"
        ) as mock_log:
            MockEmail.send.return_value = False
            MockEmail.breaker_state.return_value = CircuitState.OPEN.value

            result = svc.send_email("alice@homefinder.gr", "2FA Code", "987654")

        assert result is False
        mock_log.warning.assert_called_once()
        warning_text = str(mock_log.warning.call_args)
        # Warning must reference circuit state and SMS fallback
        assert "circuit" in warning_text.lower() or "SMS" in warning_text

    def test_circuit_transitions_to_half_open_after_recovery_timeout(self):
        """After recovery_timeout elapses, next state probe yields HALF_OPEN."""
        cb = CircuitBreaker(
            failure_threshold=3, recovery_timeout=0.05, name="CB_HalfOpen"
        )

        def fail():
            raise ConnectionError("down")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(fail)

        assert cb.state == CircuitState.OPEN
        time.sleep(0.07)
        assert cb.state == CircuitState.HALF_OPEN

    def test_successful_probe_in_half_open_resets_to_closed(self):
        """A successful call during HALF_OPEN resets circuit back to CLOSED."""
        cb = CircuitBreaker(
            failure_threshold=3, recovery_timeout=0.05, name="CB_Reset"
        )

        def fail():
            raise ConnectionError("down")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(fail)

        time.sleep(0.07)
        assert cb.state == CircuitState.HALF_OPEN

        cb.call(lambda: "probe ok")
        assert cb.state == CircuitState.CLOSED
        assert cb._failures == 0

    def test_failure_counter_resets_on_success(self):
        """A successful call after partial failures resets the failure count."""
        cb = CircuitBreaker(failure_threshold=3, name="CB_CountReset")

        def fail():
            raise ConnectionError("x")

        with pytest.raises(ConnectionError):
            cb.call(fail)   # failures = 1

        cb.call(lambda: "ok")   # success → reset
        assert cb._failures == 0
        assert cb.state == CircuitState.CLOSED