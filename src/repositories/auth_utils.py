"""
Module: repositories.auth_utils
Description: Manages authentication security controls, including one-time TOTP hash validation 
             and brute-force request throttling counters.
References:
  - SRS FR-02 / UC-02: Support user login using 2-Factor Authentication (2FA) via email tokens[cite: 119, 159, 169].
  - SRS NFR-01 / NFR-02: Strict security controls, sliding window rate limits, and single active sessions[cite: 130, 146, 147].
  - SDS §2.2 / §2.2.1 / §2.2.3: Inbound verification pipelines, token storage cryptographic hashing, and 429 response structures[cite: 8, 38, 39, 40, 45, 46, 47].
"""

import hashlib
from datetime import datetime, timedelta
from models import get_db
from .base import BaseRepository

class Pending2FARepository(BaseRepository):
    
    def store(self, user_id: int, token: str):
        """
        Computes SHA-256 hash of plaintext TOTP code and saves it with a 5-minute hard expiry.
        Ref: SDS §2.1 Table 1 / §2.2.3 (Cryptographic isolation of raw session secrets)[cite: 23, 45, 46, 47].
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        self._exec(
            "INSERT INTO pending_2fa (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, token_hash, expires),
        )

    def verify_and_consume(self, user_id: int, token: str) -> bool:
        """
        Validates hash integrity window and atomically deletes row to prevent token reuse.
        Ref: SDS §2.1 / §2.2.3 (Single-use activation flow / Replay-attack protection)[cite: 23, 46, 47].
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = self._q(
            "SELECT id FROM pending_2fa WHERE user_id = ? AND token_hash = ? AND expires_at > ?",
            (user_id, token_hash, now),
        )
        if row:
            # Atomic deletion guarantees immediate token consumption (Ref: SDS Figure 3 sequence frame) [cite: 46, 51]
            self._exec("DELETE FROM pending_2fa WHERE id = ?", (row["id"],))
            return True
        return False

    def purge_expired(self) -> int:
        """
        Housekeeping cleanup to evict stale unconsumed security tokens from tables.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            cur = conn.execute("DELETE FROM pending_2fa WHERE expires_at < ?", (now,))
            return cur.rowcount

class LoginAttemptRepository(BaseRepository):
    
    def record(self, username: str, ip: str = ""):
        """
        Logs an entry for auditing brute-force vectors after credential check misfires.
        Ref: SDS §2.1 Table 1 / §2.2.1 (Failed attempt aggregation)[cite: 24, 27, 38].
        """
        self._exec("INSERT INTO login_attempt (username, ip_address) VALUES (?, ?)", (username, ip))

    def is_rate_limited(self, username: str, max_attempts: int = 3, window_minutes: int = 5) -> bool:
        """
        Checks sliding timeline threshold window to trigger an immediate HTTP 429 restriction.
        Ref: SDS §1 / §2.2.1 (Rate limit evaluation constraint: Max 3 attempts / 5 mins)[cite: 8, 39, 40].
        """
        cutoff = (datetime.now() - timedelta(minutes=window_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        c = self._q(
            "SELECT COUNT(*) FROM login_attempt WHERE username = ? AND created_at > ?",
            (username, cutoff), scalar=True,
        )
        return bool(c and c >= max_attempts)

    def reset(self, username: str):
        """
        Clears the brute-force attempt buffer counter immediately following a successful 2FA entry.
        Ref: SDS §2.2.1 (Successful validation state clearing)[cite: 40].
        """
        self._exec("DELETE FROM login_attempt WHERE username = ?", (username,))

    def purge_old(self, keep_days: int = 1) -> int:
        """
        Maintains structural query efficiency by purging temporary connection block telemetry data.
        """
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            cur = conn.execute("DELETE FROM login_attempt WHERE created_at < ?", (cutoff,))
            return cur.rowcount