"""
Module: repositories.notification
Description: Controls storage layers for tracking in-app user receipt logs and system alert status flags.
References:
  - SRS FR-08: System notifies users when properties or transaction statuses change state[cite: 125].
  - SDS §2.1 Table 1: Traceability matrix for NOTIFICATION record targets[cite: 31, 32].
  - SDS §2.3: Receipt and transactional alerts triggered outside the core payment database write lock[cite: 57].
"""

from .base import BaseRepository

class NotificationRepository(BaseRepository):
    
    def create(self, user_id: int, title: str, message: str):
        """
        Appends an unread operational notification entry for target user views.
        Ref: SDS §2.3 (Emitted outside transaction boundaries to secure payment atomicity)[cite: 57].
        """
        self._exec(
            "INSERT INTO notification (user_id, title, message) VALUES (?, ?, ?)",
            (user_id, title, message),
        )

    def find_by_user(self, user_id: int, unread_only: bool = False) -> list[dict]:
        """
        Gathers system notifications assigned to an authenticated web consumer portal view.
        """
        sql = "SELECT * FROM notification WHERE user_id = ?"
        if unread_only:
            sql += " AND is_read = 0"
        sql += " ORDER BY created_at DESC"
        return self._q(sql, (user_id,), many=True)

    def mark_read(self, user_id: int):
        """
        Atomically updates pending structural messages into read states for an individual profile.
        """
        self._exec("UPDATE notification SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))

    def unread_count(self, user_id: int) -> int:
        """
        Gathers simple notification counters for real-time navigation badge counters.
        """
        return self._q("SELECT COUNT(*) FROM notification WHERE user_id = ? AND is_read = 0", (user_id,), scalar=True) or 0

    def delete_for_user_by_title(self, user_id: int, title: str):
        """
        Administrative housecleaning utility to purge diagnostic notifications from tables.
        """
        self._exec("DELETE FROM notification WHERE user_id = ? AND title = ?", (user_id, title))