"""
Module: repositories.appointment
Description: Handles data access operations for scheduling and managing viewing appointments.
References:
  - SRS FR-06: The system shall allow users to schedule property viewings directly through the portal.
  - SDS Table 1: ERD Entity Traceability (Optimistic Locking & status fields).
  - SDS §2.3: Cascade cancellations when property status updates to unavailable.
"""

import logging
from .base import BaseRepository

logger = logging.getLogger(__name__)

class AppointmentRepository(BaseRepository):
    
    def create(self, user_id: int, property_id: int, scheduled_at: str, notes: str = "") -> int | None:
        """
        Inserts a new property viewing appointment.
        Ref: SRS FR-06 / UC-05 (Schedule Viewing)
        """
        try:
            return self._exec(
                "INSERT INTO appointment (user_id, property_id, scheduled_at, notes) VALUES (?, ?, ?, ?)",
                (user_id, property_id, scheduled_at, notes),
            )
        except Exception as e:
            # Handle real-time calendar slot double-booking constraints (Ref: SRS UC-05 Notes)
            if "UNIQUE constraint failed" in str(e):
                logger.warning("Concurrency conflict on appointment scheduling for property %d at %s", property_id, scheduled_at)
                return None
            raise

    def find_by_user(self, user_id: int) -> list[dict]:
        """
        Fetches all scheduled appointments for a specific authenticated user.
        """
        return self._q(
            """SELECT a.*, p.title as property_title, p.location as property_location
               FROM appointment a
               JOIN property p ON a.property_id = p.id
               WHERE a.user_id = ?
               ORDER BY a.scheduled_at DESC""",
            (user_id,), many=True,
        )

    def get_all_appointments(self) -> list[dict]:
        """
        Administrative retrieval of all system-wide viewing appointments.
        Ref: SRS FR-10 (Admin manage user interactions)
        """
        return self._q(
            """SELECT a.*, p.title as property_title, u.username, up.email_enc, up.full_name
               FROM appointment a
               JOIN property p ON a.property_id = p.id
               JOIN user u ON a.user_id = u.id
               LEFT JOIN user_profile up ON u.id = up.user_id
               ORDER BY a.scheduled_at DESC""",
            many=True,
        )

    def update_status(self, appt_id: int, new_status: str, current_version: int) -> bool:
        """
        Updates the appointment state using Optimistic Locking.
        Ref: SDS Table 1 (APPOINTMENT schema concurrency control)
        """
        from models import get_db
        with get_db() as conn:
            cur = conn.execute(
                "UPDATE appointment SET status = ?, version = version + 1 WHERE id = ? AND version = ?",
                (new_status, appt_id, current_version),
            )
            return cur.rowcount == 1

    def cancel_for_property(self, property_id: int):
        """
        Bulk cancels pending viewings when a property becomes unavailable.
        Ref: SDS §2.3 (Payment transaction side effects / atomic updates)
        """
        self._exec("UPDATE appointment SET status = 'cancelled' WHERE property_id = ? AND status = 'pending'", (property_id,))