"""
Module: repositories.session
Description: Low-level lookup engine evaluating security active state parameters.
References:
  - SRS FR-02 / NFR-02: Enforce a single active authentication context session allocation per client.
  - SDS §1.1 / §2.2.4: Signed HTTP-Only cookie verification contexts and multi-device exclusion checks.
"""

from datetime import datetime, timedelta, timezone
from .base import BaseRepository

class SessionRepository(BaseRepository):
    
    def create(self, user_id: int, token: str, ttl_hours: int = 24):
        """
        Registers an explicit context lease block assigning state validation variables to a user profile.
        Ref: SDS §2.2.4 (Establishing 24-Hour token-hash validation links).
        """
        exp = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
        self._exec(
            "INSERT INTO user_session (user_id, session_token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, exp),
        )

    def invalidate_all(self, user_id: int):
        """
        Purges active connection leases for a specific account index.
        Ref: SRS NFR-02 / SDS §2.2.4 (Enforcing the single active session rule dynamically).
        """
        self._exec("DELETE FROM user_session WHERE user_id = ?", (user_id,))