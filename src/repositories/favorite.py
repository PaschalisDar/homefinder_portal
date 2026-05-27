"""
Module: repositories.favorite
Description: Handles data access operations for managing user-specific personal favorite property lists.
References:
  - SRS FR-05: The system shall allow users to save specific properties to a personal favorites list[cite: 122].
  - SDS §2.1 Table 1: Traceability matrix mapping PROPERTY configurations to user interactions[cite: 26, 29].
"""

from .base import BaseRepository

class FavoriteRepository(BaseRepository):
    
    def add(self, user_id: int, property_id: int):
        """
        Inserts a property entry into the user's personal favorites list.
        Ignores operations if the bookmark linkage already exists.
        """
        self._exec("INSERT OR IGNORE INTO favorite (user_id, property_id) VALUES (?, ?)", (user_id, property_id))

    def remove(self, user_id: int, property_id: int):
        """
        Removes a property entry from the user's personal favorites list.
        """
        self._exec("DELETE FROM favorite WHERE user_id = ? AND property_id = ?", (user_id, property_id))

    def is_favorite(self, user_id: int, property_id: int) -> bool:
        """
        Checks if a concrete property structure is currently saved by a specific user.
        """
        c = self._q("SELECT COUNT(*) FROM favorite WHERE user_id = ? AND property_id = ?", (user_id, property_id), scalar=True)
        return bool(c and c > 0)

    def find_by_user(self, user_id: int) -> list[dict]:
        """
        Fetches all bookmarked property rows for an authenticated user catalog.
        """
        return self._q(
            """SELECT p.* FROM favorite f
               JOIN property p ON f.property_id = p.id
               WHERE f.user_id = ?""",
            (user_id,), many=True,
        )