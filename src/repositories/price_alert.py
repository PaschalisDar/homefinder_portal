"""
Module: repositories.price_alert
Description: Data access logic handling subscription registries for listing updates and alerts.
References:
  - SRS FR-08: The system shall allow users to subscribe to notifications when a property is unavailable.
  - SDS §2.1 Table 1: Traceability for automated listing event structures.
"""

from .base import BaseRepository

class PriceAlertRepository(BaseRepository):
    
    def subscribe(self, user_id: int, property_id: int):
        """
        Registers an interest subscription binding for real-time notification alerts.
        Ref: SRS UC-10 (Subscribe to Notifications).
        """
        self._exec("INSERT OR IGNORE INTO price_alert (user_id, property_id, threshold) VALUES (?, ?, 0)", (user_id, property_id))

    def unsubscribe(self, user_id: int, property_id: int):
        """
        Removes an active notification subscription bond.
        """
        self._exec("DELETE FROM price_alert WHERE user_id = ? AND property_id = ?", (user_id, property_id))

    def is_subscribed(self, user_id: int, property_id: int) -> bool:
        """
        Queries flag states to resolve interface layout rendering.
        """
        c = self._q("SELECT COUNT(*) FROM price_alert WHERE user_id = ? AND property_id = ?", (user_id, property_id), scalar=True)
        return bool(c and c > 0)

    def find_by_user(self, user_id: int) -> list[dict]:
        """
        Fetches all active listing monitoring structures associated with a client profile.
        """
        return self._q(
            """SELECT pa.*, p.title as property_title, p.price, p.category, p.location
               FROM price_alert pa
               JOIN property p ON pa.property_id = p.id
               WHERE pa.user_id = ?
               ORDER BY pa.created_at DESC""",
            (user_id,), many=True,
        )

    def find_subscribers_for_property(self, property_id: int) -> list[dict]:
        """
        Resolves targeted email/SMS notification queues when an un-availability update event triggers.
        Ref: SRS FR-08 / SDS §3.3 (Circuit breaker fallback context).
        """
        return self._q(
            """SELECT pa.user_id, up.email_enc, u.username
               FROM price_alert pa
               JOIN user u ON pa.user_id = u.id
               LEFT JOIN user_profile up ON u.id = up.user_id
               WHERE pa.property_id = ?""",
            (property_id,), many=True,
        )

    def find_by_category(self, category: str) -> list[dict]:
        """
        Resolves general group demographics matching specific portfolio taxonomy buckets.
        """
        return self._q(
            """SELECT DISTINCT pa.user_id, up.email_enc, u.username
               FROM price_alert pa
               JOIN property p ON pa.property_id = p.id
               JOIN user u ON pa.user_id = u.id
               LEFT JOIN user_profile up ON u.id = up.user_id
               WHERE p.category = ?""",
            (category,), many=True,
        )