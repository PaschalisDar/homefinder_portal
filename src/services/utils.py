"""
services/utils.py
Utility functions including TOTP generation and Circuit Breaker implementation.
"""

import base64
import os
import time
import logging
from enum import Enum
from typing import Optional

from cryptography.hazmat.primitives.twofactor.totp import TOTP
from cryptography.hazmat.primitives.hashes import SHA1

logger = logging.getLogger(__name__)

def _generate_totp_secret() -> str:
    # Generates secret for 2FA requirement.
    # Ref: SRS FR-02 (2-Factor Authentication).
    return base64.b32encode(os.urandom(20)).decode()


def _make_totp(secret_b32: str) -> TOTP:
    key = base64.b32decode(secret_b32)
    return TOTP(key, 6, SHA1(), 30)


def generate_totp_token(secret_b32: str) -> str:
    # Generates a 6-digit TOTP token valid for 30 seconds.
    # Ref: SRS NFR-01 (Performance constraint for 2FA delivery).
    totp  = _make_totp(secret_b32)
    token = totp.generate(int(time.time()))
    return token.decode()


def verify_totp_token(secret_b32: str, token: str) -> bool:
    # Verifies the token to authenticate the user securely with a ±1 step window.
    # Ref: SRS FR-02 (User login using 2FA), SDS §2.2 (Authentication Flow).
    totp = _make_totp(secret_b32)
    now  = int(time.time())
    for delta in (-30, 0, 30):
        try:
            totp.verify(token.encode(), now + delta)
            return True
        except Exception:
            continue
    return False


def totp_provisioning_uri(secret_b32: str, username: str) -> str:
    return (
        f"otpauth://totp/HomeFinder%3A{username}"
        f"?secret={secret_b32}&issuer=HomeFinder&algorithm=SHA1&digits=6&period=30"
    )


class CircuitState(Enum):
    # States for the Circuit Breaker pattern.
    # Ref: SDS §3.3 (Circuit Breaker states: CLOSED / OPEN / HALF-OPEN).
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    # Implements the Circuit Breaker pattern to protect the 2FA delivery SLA.
    # Ref: SDS §3.3 (Circuit Breaker - Email Service).
    def __init__(
        self,
        failure_threshold: int  = 3,
        recovery_timeout:  float = 60.0,
        name: str = "CircuitBreaker",
    ):
        self._threshold  = failure_threshold
        self._timeout    = recovery_timeout
        self._name       = name
        self._failures   = 0
        self._state      = CircuitState.CLOSED
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._opened_at >= self._timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("[%s] -> HALF_OPEN", self._name)
        return self._state

    def call(self, func, *args, **kwargs):
        st = self.state
        if st == CircuitState.OPEN:
            raise RuntimeError(f"[{self._name}] Circuit OPEN - service unavailable")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise exc

    def _on_success(self):
        self._failures = 0
        self._state    = CircuitState.CLOSED

    def _on_failure(self):
        self._failures += 1
        logger.warning("[%s] failure %d/%d", self._name, self._failures, self._threshold)
        if self._failures >= self._threshold:
            self._state     = CircuitState.OPEN
            self._opened_at = time.time()
            logger.error("[%s] -> OPEN", self._name)


class EmailService:
    # Wraps the SMTP client in a Circuit Breaker.
    # Ref: SDS §3.3 (Circuit Breaker), SRS NFR-01 (Delivery within 30s).
    _breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60, name="EmailCB")

    @classmethod
    def send(cls, to_addr: str, subject: str, body: str) -> bool:
        def _send():
            logger.info("[EMAIL] To: %s | Subject: %s", to_addr, subject)
            s_to      = to_addr.encode("ascii", "replace").decode("ascii")
            s_subject = subject.encode("ascii", "replace").decode("ascii")
            s_body    = body.encode("ascii", "replace").decode("ascii")

            print(f"\n{'='*60}")
            print(f"  [EMAIL]   : {s_to}")
            print(f"  Subject   : {s_subject}")
            print(f"  Body      : {s_body}")
            print(f"{'='*60}\n")
            
            totp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "totp_code.txt")
            os.makedirs(os.path.dirname(totp_path), exist_ok=True)
            with open(totp_path, "w") as f:
                f.write(s_body)
            return True

        try:
            return cls._breaker.call(_send)
        except RuntimeError as e:
            logger.error("EmailService circuit open: %s", e)
            return False

    @classmethod
    def breaker_state(cls) -> str:
        return cls._breaker.state.value


class SMSService:
    # Fallback mechanism when EmailService is in OPEN state.
    # Ref: SDS §3.3 (Circuit Breaker SMS fallback mechanism).
    @staticmethod
    def send(to_number: str, message: str) -> bool:
        logger.info("[SMS] To: %s | %s", to_number, message)
        print(f"\n[SMS] -> {to_number}: {message}\n")
        return True