"""
Module: repositories.inquiry
Description: Manages database interaction routines for submitting and reviewing specific property inquiries.
References:
  - SRS FR-07: The system shall allow users to submit inquiries regarding specific property listings[cite: 124].
  - SRS FR-09: Generates supervisor metrics derived from trend data and listing interaction logs[cite: 126].
  - SDS §2.1 Table 1: Traceability for INQUIRY relation constraints linked to users and properties[cite: 26, 29].
"""

from .base import BaseRepository

class InquiryRepository(BaseRepository):
    
    def create(self, user_id: int, property_id: int, message: str) -> int:
        """
        Persists a user booking question or property inquiry payload.
        Ref: SRS FR-07 / UC-06 (Submit Inquiry)[cite: 124, 163].
        """
        return self._exec(
            "INSERT INTO inquiry (user_id, property_id, message) VALUES (?, ?, ?)",
            (user_id, property_id, message),
        )

    def find_by_user(self, user_id: int) -> list[dict]:
        """
        Retrieves all submission entries authored by a specific user account.
        """
        return self._q(
            """SELECT i.*, p.title as property_title
               FROM inquiry i
               JOIN property p ON i.property_id = p.id
               WHERE i.user_id = ?
               ORDER BY i.created_at DESC""",
            (user_id,), many=True,
        )

    def get_all(self) -> list[dict]:
        """
        Administrative retrieval of all system-wide listings inquiries.
        Ref: SRS FR-10 (Admin overview of user interactions)[cite: 127].
        """
        return self._q(
            """SELECT i.*, p.title as property_title, u.username as user_username
               FROM inquiry i
               JOIN property p ON i.property_id = p.id
               JOIN user u ON i.user_id = u.id
               ORDER BY i.created_at DESC""",
            many=True,
        )

    def respond(self, inquiry_id: int, response: str):
        """
        Updates an inquiry record with administrative commentary text.
        Ref: SRS FR-10 (Admin response management)[cite: 127].
        """
        self._exec("UPDATE inquiry SET response = ?, status = 'responded' WHERE id = ?", (response, inquiry_id))

    def count_open(self) -> int:
        """
        Aggregates unaddressed customer interactions for management backlog dashboards.
        Ref: SRS FR-09 / UC-09 (Supervisor search and interaction statistics tracking)[cite: 126, 165].
        """
        return self._q("SELECT COUNT(*) FROM inquiry WHERE status = 'open'", scalar=True) or 0

    def find_by_id(self, inquiry_id: int) -> dict | None:
        """
        Locates a single structural inquiry entry by its integer record identifier.
        """
        return self._q("SELECT * FROM inquiry WHERE id = ?", (inquiry_id,))