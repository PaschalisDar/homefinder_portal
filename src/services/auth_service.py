"""
services/auth_service.py
Implements the two-phase TOTP-based login protocol and user registration.
Ref: SDS §2.2 (Authentication & Security Flow).
"""

import jwt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import JWT_SECRET, hash_password, verify_password
from repositories import (
    UserRepository, SessionRepository, AuditLogRepository,
    Pending2FARepository, LoginAttemptRepository
)
from dtos import AuthDTO, VerificationDTO
from .exceptions import RateLimitExceeded, ValidationError
from .utils import (
    _generate_totp_secret, generate_totp_token,
    verify_totp_token, totp_provisioning_uri
)
from .notification_service import NotificationService

logger = logging.getLogger(__name__)

class AuthService:
    PRE_AUTH_TTL  = 90
    ACCESS_TTL_H  = 24

    def __init__(self):
        self._users     = UserRepository()
        self._sessions  = SessionRepository()
        self._audit     = AuditLogRepository()
        self._notif     = NotificationService()
        self._pending   = Pending2FARepository()
        self._attempts  = LoginAttemptRepository()

    def register(
        self,
        username:     str,
        password:     str,
        email:        str,
        full_name:    str  = "",
        gdpr_consent: bool = False,
        role:         str  = "user",
    ) -> dict:
        # Handles user registration with secure password.
        # Ref: SRS FR-01, SRS UC-01.
        if self._users.find_by_username(username):
            return {"ok": False, "error": "Username already taken"}
        if self._users.find_by_email(email):
            return {"ok": False, "error": "Email already registered"}

        pw_hash = hash_password(password)
        secret  = _generate_totp_secret()
        user_id = self._users.create(
            username, pw_hash, email, role, full_name, gdpr_consent
        )
        self._users.update_totp_secret(user_id, secret)
        self._audit.log("register", user_id, f"New {role} account: {username}")
        return {
            "ok":           True,
            "user_id":      user_id,
            "totp_secret":  secret,
            "totp_uri":     totp_provisioning_uri(secret, username),
        }

    def initiate_login(self, username: str, password: str, ip: str = "") -> dict:
        # Phase 1: Validates credentials and generates TOTP.
        # Enforces rate limiting (3 attempts per 5 mins). Ref: SDS §2.2.1.
        if self._attempts.is_rate_limited(username):
            self._audit.log("login_rate_limited", detail=f"user={username}", ip_address=ip)
            raise RateLimitExceeded(
                "Too many login attempts. Please try again in a few minutes."
            )

        # Deserializes payload into immutable DTO. Ref: SDS §2.2.2.
        try:
            dto = AuthDTO(username=username.strip(), password=password, ip_address=ip)
            dto.validate()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        logger.info("[AUTH] Login attempt for user: %s", dto.username)

        user = self._users.find_by_username(dto.username)
        if not user or not user.get("is_active"):
            self._attempts.record(dto.username, ip)
            self._audit.log("login_fail", detail=f"Unknown user: {dto.username}", ip_address=ip)
            return {"ok": False, "error": "Invalid credentials"}

        if not verify_password(dto.password, user["password_hash"]):
            self._attempts.record(dto.username, ip)
            self._audit.log("login_fail", user["id"], "Bad password", ip)
            return {"ok": False, "error": "Invalid credentials"}

        pre_token = jwt.encode(
            {
                "sub":      str(user["id"]),
                "phase":    "pre_auth",
                "exp":      datetime.now(timezone.utc) + timedelta(seconds=self.PRE_AUTH_TTL),
            },
            JWT_SECRET,
            algorithm="HS256",
        )

        secret = user.get("totp_secret")
        if secret:
            # Generates TOTP token and stores its hash with a 5-min expiry. Ref: SDS §2.2.3.
            token = generate_totp_token(secret)
            self._pending.store(user["id"], token)

            email = ""
            try:
                # Retrieves encrypted PII for 2FA dispatch. Ref: SRS NFR-03 (GDPR).
                profile = self._users.find_profile(user["id"])
                email   = profile.get("email", "") if profile else ""
            except Exception as exc:
                logger.warning(
                    "[AUTH] Profile lookup/decryption failed for user '%s': %s",
                    dto.username, exc,
                )

            if email:
                logger.info("[AUTH] Dispatching 2FA token to: %s", email)
                self._notif.send_2fa_token(email, token, dto.username)
            else:
                logger.warning(
                    "[AUTH] No email found for user '%s' — 2FA token NOT dispatched via email.",
                    dto.username,
                )
                print(
                    f"\n>>> [2FA FALLBACK] User: {dto.username!r} | Token: {token} <<<\n",
                    flush=True,
                )
        else:
            logger.warning("[AUTH] No TOTP secret found for user %s - skipping 2FA", dto.username)

        self._audit.log("login_phase1", user["id"], "Credential verified", ip)
        return {"ok": True, "pre_auth_token": pre_token}

    def verify_2fa(self, pre_auth_token: str, totp_token: str, ip: str = "") -> dict:
        # Phase 2: Validates the TOTP token and establishes the session.
        # Deserializes payload into immutable DTO. Ref: SDS §2.2.2.
        try:
            dto = VerificationDTO(
                pre_auth_token=pre_auth_token,
                totp_token=totp_token,
                ip_address=ip,
            )
            dto.validate()
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        try:
            claims = jwt.decode(
                dto.pre_auth_token, JWT_SECRET, algorithms=["HS256"],
                leeway=timedelta(seconds=10),
            )
        except jwt.ExpiredSignatureError:
            return {"ok": False, "error": "Session expired — please log in again"}
        except jwt.InvalidTokenError:
            return {"ok": False, "error": "Invalid session token"}

        if claims.get("phase") != "pre_auth":
            return {"ok": False, "error": "Invalid token phase"}

        user_id = int(claims["sub"])
        user    = self._users.find_by_id(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}

        # Verifies single-use time-bounded token hash. Ref: SDS §2.2.3.
        token_ok = self._pending.verify_and_consume(user_id, dto.totp_token)
        if not token_ok:
            secret = user.get("totp_secret")
            token_ok = bool(secret and verify_totp_token(secret, dto.totp_token.strip()))

        if not token_ok:
            self._audit.log("2fa_fail", user_id, "Bad TOTP token", ip)
            return {"ok": False, "error": "Invalid or expired authentication code"}

        # Invalidates previously active sessions (Single active session rule).
        # Ref: SRS NFR-02, SDS §2.2.4.
        self._sessions.invalidate_all(user_id)

        # Generates 24-hour HS256 JWT for secure HttpOnly cookie delivery. Ref: SDS §2.2.4.
        access_token = jwt.encode(
            {
                "sub":  str(user_id),
                "role": user["role"],
                "exp":  datetime.now(timezone.utc) + timedelta(hours=self.ACCESS_TTL_H),
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        self._sessions.create(user_id, access_token, ttl_hours=self.ACCESS_TTL_H)
        self._attempts.reset(user["username"])
        self._audit.log("login_success", user_id, "2FA verified", ip)
        return {
            "ok":           True,
            "access_token": access_token,
            "user_id":      user_id,
            "role":         user["role"],
            "username":     user["username"],
        }

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        try:
            return jwt.decode(
                token, JWT_SECRET, algorithms=["HS256"],
                leeway=timedelta(seconds=10),
            )
        except jwt.InvalidTokenError:
            return None