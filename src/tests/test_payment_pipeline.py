# tests/test_payment_pipeline.py
import pytest
from unittest.mock import patch, call
from services.exceptions import PaymentDeclined, ValidationError


class TestPaymentPipeline:
    """
    Mock ExternalPaymentGateway; verify that a successful payment executes
    all four ACID operations on the SAME connection object.
    """

    @staticmethod
    def _charge_ok():
        return {"ok": True, "transaction_id": "TESTREF0000000A"}

    def test_successful_payment_returns_receipt(self, payment_svc):
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            result = payment_svc.process(user_id=1, property_id=1, amount=250_000)
        assert result["ok"] is True
        assert result["reference"] == "TESTREF0000000A"

    def test_property_marked_sold_within_transaction(self, payment_svc, patched_get_db):
        """UPDATE property SET is_available=0, sold_at=... must be called."""
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            payment_svc.process(user_id=1, property_id=1, amount=250_000)

        patched_get_db.execute.assert_any_call(
            "UPDATE property SET is_available = 0, sold_at = datetime('now') WHERE id = ?",
            (1,),
        )

    def test_pending_appointments_cancelled_within_transaction(
        self, payment_svc, patched_get_db
    ):
        """UPDATE appointment SET status='cancelled' must be called."""
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            payment_svc.process(user_id=1, property_id=1, amount=250_000)

        patched_get_db.execute.assert_any_call(
            "UPDATE appointment SET status = 'cancelled' "
            "WHERE property_id = ? AND status = 'pending'",
            (1,),
        )

    def test_audit_log_written_within_transaction(self, payment_svc, patched_get_db):
        """INSERT INTO audit_log with action='payment_success' must be called."""
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            payment_svc.process(user_id=2, property_id=1, amount=250_000)

        audit_call = call(
            """INSERT INTO audit_log (user_id, action, detail)
                       VALUES (?, 'payment_success', ?)""",
            (2, f"€{250_000:,.2f} for property #1"),
        )
        patched_get_db.execute.assert_any_call(*audit_call.args, **audit_call.kwargs)

    def test_payment_record_inserted_within_transaction(self, payment_svc, patched_get_db):
        """INSERT INTO payment with status='completed' must be called."""
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            payment_svc.process(user_id=1, property_id=1, amount=250_000)

        sql_calls = [str(c) for c in patched_get_db.execute.call_args_list]
        assert any("INSERT INTO payment" in s and "completed" in s for s in sql_calls)

    def test_all_four_acid_writes_share_one_db_context(
        self, payment_svc, patched_get_db
    ):
        """
        All writes (INSERT payment, UPDATE property, UPDATE appointment,
        INSERT audit_log) must go through the same connection object,
        guaranteeing atomicity.
        """
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            payment_svc.process(user_id=1, property_id=1, amount=250_000)

        assert patched_get_db.execute.call_count >= 4, (
            "Expected ≥4 SQL calls (INSERT payment, UPDATE property, "
            "UPDATE appointment, INSERT audit_log) on the same connection"
        )

    def test_receipt_notification_sent_to_buyer(self, payment_svc):
        """Buyer must receive a 'Payment Confirmed' in-app notification."""
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value=self._charge_ok(),
        ):
            payment_svc.process(user_id=1, property_id=1, amount=250_000)

        payment_svc._notifs.create.assert_called_once()
        args = payment_svc._notifs.create.call_args[0]
        assert args[0] == 1                 # user_id
        assert "Payment Confirmed" in args[1]

    def test_declined_gateway_raises_and_makes_no_db_writes(
        self, payment_svc, patched_get_db
    ):
        """Declined charge ⟹ PaymentDeclined raised; zero DB mutations."""
        with patch(
            "services.payment_service.ExternalPaymentGateway.charge",
            return_value={"ok": False, "error": "Card declined"},
        ):
            with pytest.raises(PaymentDeclined):
                payment_svc.process(user_id=1, property_id=1, amount=250_000)

        patched_get_db.execute.assert_not_called()

    def test_property_not_found_raises_validation_error(self, payment_svc):
        """Unknown property_id ⟹ ValidationError before gateway is contacted."""
        payment_svc._props.find_by_id.return_value = None

        with patch("services.payment_service.ExternalPaymentGateway.charge") as gw:
            with pytest.raises(ValidationError, match="Property not found"):
                payment_svc.process(user_id=1, property_id=999, amount=100)

        gw.assert_not_called()