"""
Module: repositories.payment
Description: Direct interaction layer for reading and persisting structural booking/premium fees.
References:
  - SRS FR-11: The system shall process secure payments via credit card or bank transfer.
  - SDS §2.3: Enforces a strict validation and synchronous transaction pipeline to satisfy ACID properties.
"""

from .base import BaseRepository

class PaymentRepository(BaseRepository):
    
    def get_all(self) -> list[dict]:
        """
        Administrative lookup to query all processed payment logs across the platform.
        Ref: SRS FR-10 (Admin audit overview).
        """
        return self._q(
            """SELECT p.*, pr.title as property_title, u.username as user_username
               FROM payment p
               JOIN property pr ON p.property_id = pr.id
               JOIN user u ON p.user_id = u.id
               ORDER BY p.created_at DESC""",
            many=True,
        )

    def find_by_user(self, user_id: int) -> list[dict]:
        """
        Retrieves payment receipt histories for a specific authenticated customer account view.
        Ref: SDS §2.3 (ReceiptDTO boundary mapping context).
        """
        return self._q(
            """SELECT p.*, pr.title as property_title
               FROM payment p
               JOIN property pr ON p.property_id = pr.id
               WHERE p.user_id = ?
               ORDER BY p.created_at DESC""",
            (user_id,), many=True,
        )

    def total_revenue(self) -> float:
        """
        Aggregates financial statistics for operational performance reporting.
        Ref: SRS FR-09 / UC-09 (Supervisor analytical metric data sources).
        """
        return self._q("SELECT SUM(amount) FROM payment WHERE status = 'completed'", scalar=True) or 0.0