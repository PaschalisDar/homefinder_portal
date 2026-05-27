"""
services/payment_service.py
ACID Compliant payment infrastructure mapping transactions to payment gateways.
"""

import uuid
import logging
from models import get_db
from repositories import PaymentRepository, PropertyRepository, NotificationRepository, AuditLogRepository
from dtos import PaymentDTO, ReceiptDTO
from .exceptions import PaymentDeclined, ValidationError

logger = logging.getLogger(__name__)

class ExternalPaymentGateway:
    @staticmethod
    def charge(amount: float, card_token: str = "demo_token") -> dict:
        if amount <= 0:
            return {"ok": False, "error": "Invalid amount"}
        return {
            "ok":             True,
            "transaction_id": str(uuid.uuid4()).replace("-", "").upper()[:16],
        }

class PaymentService:
    def __init__(self):
        self._payments = PaymentRepository()
        self._props    = PropertyRepository()
        self._notifs   = NotificationRepository()
        self._audit    = AuditLogRepository()

    def process(self, user_id: int, property_id: int, amount: float, method: str = "credit_card") -> dict:
        try:
            dto = PaymentDTO(
                user_id     = int(user_id),
                property_id = int(property_id),
                amount      = float(amount),
                method      = method,
                card_token  = "demo_token",
            )
            dto.validate()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        prop = self._props.find_by_id(dto.property_id)
        if not prop:
            raise ValidationError("Property not found")

        gateway_result = ExternalPaymentGateway.charge(dto.amount, dto.card_token)
        if not gateway_result["ok"]:
            raise PaymentDeclined(gateway_result.get("error", "Payment declined"))

        unique_transaction_id = gateway_result["transaction_id"]
        payment_id = None

        try:
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO payment (user_id, property_id, amount, payment_method, reference, status)
                       VALUES (?, ?, ?, ?, ?, 'completed')""",
                    (dto.user_id, dto.property_id, dto.amount, dto.method, unique_transaction_id),
                )
                conn.execute("UPDATE property SET is_available = 0, sold_at = datetime('now') WHERE id = ?", (dto.property_id,))
                conn.execute("UPDATE appointment SET status = 'cancelled' WHERE property_id = ? AND status = 'pending'", (dto.property_id,))
                conn.execute(
                    """INSERT INTO audit_log (user_id, action, detail)
                       VALUES (?, 'payment_success', ?)""",
                    (dto.user_id, f"€{dto.amount:,.2f} for property #{dto.property_id}"),
                )
                payment_id = conn.execute("SELECT id FROM payment WHERE reference = ?", (unique_transaction_id,)).fetchone()[0]
        except Exception as exc:
            logger.error("Payment DB insert failed: %s", exc)
            return {"ok": False, "error": str(exc)}

        try:
            self._notifs.create(
                dto.user_id,
                "Payment Confirmed",
                f"Payment of €{dto.amount:,.2f} for '{prop['title']}' received. Ref: {unique_transaction_id}",
            )
        except Exception as exc:
            logger.warning("Payment notification failed (non-critical): %s", exc)

        receipt = ReceiptDTO(
            payment_id     = payment_id,
            reference      = unique_transaction_id,
            amount         = dto.amount,
            property_id    = dto.property_id,
            property_title = prop["title"],
            status         = "completed",
        )
        return receipt.to_dict()

    def get_user_payments(self, user_id: int) -> list[dict]:
        return self._payments.find_by_user(user_id)

    def get_all_payments(self) -> list[dict]:
        return self._payments.get_all()

    def total_revenue(self) -> float:
        return self._payments.total_revenue()
