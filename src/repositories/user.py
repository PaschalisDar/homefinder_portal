"""
Module: repositories.user
Description: Coordinates access boundaries surrounding operational client structures and encrypted profile data.
References:
  - SRS FR-01 / UC-01: Allow users to register with an email and secure password.
  - SRS NFR-03: Compliance with GDPR principles collecting only minimal necessary information.
  - SDS §2.1 / §2.1 Table 1: PII separation mechanics via dedicated AES-256-GCM encryption calls.
"""

from .base import BaseRepository
from models import encrypt_pii, decrypt_pii, hash_pii

class UserRepository(BaseRepository):
    
    def find_by_username(self, username: str) -> dict | None:
        """
        Resolves core system access credentials during initial credential validation.
        """
        return self._q("SELECT * FROM user WHERE username = ?", (username,))

    def find_by_email(self, email: str) -> dict | None:
        """
        Validates profile uniqueness across encrypted fields using a deterministic HMAC index.
        Ref: SDS §2.1 (GDPR data minimisation constraints isolating PII attributes).
        """
        h = hash_pii(email)
        return self._q("SELECT * FROM user_profile WHERE email_hash = ?", (h,))

    def find_by_id(self, user_id: int) -> dict | None:
        """
        Locates foundational credential rows via direct internal key maps.
        """
        return self._q("SELECT * FROM user WHERE id = ?", (user_id,))

    def find_profile(self, user_id: int) -> dict | None:
        """
        Decrypts PII elements dynamically using verified algorithmic deciphering strategies.
        Ref: SDS Table 1 / USER_PROFILE (Decrypting AES-256-GCM strings transparently before UI presentation).
        """
        p = self._q("SELECT * FROM user_profile WHERE user_id = ?", (user_id,))
        if p and p.get("email_enc"):
            p["email"] = decrypt_pii(p["email_enc"])
        return p

    def create(self, username: str, password_hash: str, email: str, role: str = "user", full_name: str = "", gdpr_consent: bool = False) -> int:
        """
        Performs dual-table isolated inserts split securely along structural PII domain splits.
        Ref: SRS FR-01 / NFR-03 | SDS §2.1 (Isolating identity tables from operational nodes).
        """
        uid = self._exec(
            "INSERT INTO user (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        # Store isolated encrypted client profile telemetry fields securely (Ref: SDS Table 1 parameters)
        self._exec(
            "INSERT INTO user_profile (user_id, email_enc, email_hash, full_name, gdpr_consent) VALUES (?, ?, ?, ?, ?)",
            (uid, encrypt_pii(email), hash_pii(email), full_name, 1 if gdpr_consent else 0),
        )
        return uid

    def update_totp_secret(self, user_id: int, secret: str):
        """
        Saves updated authentication token secret seeds assigned to specific user verification loops.
        Ref: SRS FR-02 / UC-02 (2FA registration dependencies).
        """
        self._exec("UPDATE user SET totp_secret = ? WHERE id = ?", (secret, user_id))

    def get_all_users_with_stats(self) -> list[dict]:
        """
        Administrative dashboard overview joining authentication metrics and security statistics.
        Ref: SRS FR-10 (Admin account management capabilities).
        """
        return self._q(
            """SELECT u.id, u.username, u.role, u.is_active, u.created_at,
                      up.email_enc, up.full_name,
                      (SELECT COUNT(*) FROM login_attempt WHERE username = u.username) as recent_failed_logins,
                      (SELECT COUNT(*) FROM audit_log WHERE user_id = u.id AND action = 'login_success') as total_logins
               FROM user u
               LEFT JOIN user_profile up ON u.id = up.user_id
               ORDER BY u.created_at DESC""",
            many=True,
        )

    def toggle_user_status(self, user_id: int):
        """
        Locks or unlocks an account interface link directly from supervisor interaction matrices.
        Ref: SRS FR-10 / UC-11 (Administrative status modification workflows).
        """
        self._exec("UPDATE user SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (user_id,))

    def find_all_admins(self) -> list[dict]:
        """
        Locates active administrative profiles capable of handling explicit alert broadcasts.
        """
        return self._q("SELECT id, username FROM user WHERE role = 'admin' AND is_active = 1", many=True)