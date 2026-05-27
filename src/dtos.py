"""
dtos.py — HomeFinder Portal
Named Data Transfer Objects (DTOs) for strict data validation and isolation.

References:
- SDS Section 2.2.2: DTO Boundaries (AuthDTO, VerificationDTO).
- SDS Section 2.3: Transaction Processing (PaymentDTO, ReceiptDTO).
- SRS FR-01, FR-02, FR-11: Authentication, 2FA, and Secure Payments.

All DTOs are immutable (frozen=True) and validate upon initialization to 
ensure raw or malformed data does not reach the service or repository layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Authentication DTOs (SDS Section 2.2.2 / Figure 3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuthDTO:
    """
    Phase-1 login payload boundary.
    Carries only the fields necessary to verify credentials and initiate 2FA.
    """
    username:   str
    password:   str
    ip_address: str = ""

    def __post_init__(self):
        if not self.username or not self.username.strip():
            raise ValueError("username is required")
        if not self.password:
            raise ValueError("password is required")

    def validate(self) -> bool:
        """Satisfies SDS class-diagram contract."""
        return True   # Validation is enforced in __post_init__


@dataclass(frozen=True)
class VerificationDTO:
    """
    Phase-2 login payload boundary.
    Holds the pre-auth JWT and the 6-digit TOTP token without exposing secrets.
    """
    pre_auth_token: str
    totp_token:     str
    ip_address:     str = ""

    def __post_init__(self):
        if not self.pre_auth_token:
            raise ValueError("pre_auth_token is required")
        token = (self.totp_token or "").strip()
        if not token or len(token) != 6 or not token.isdigit():
            raise ValueError("TOTP token must be 6 digits")

    def validate(self) -> bool:
        """Satisfies SDS class-diagram contract."""
        return True


# ---------------------------------------------------------------------------
# Payment DTOs (SDS Section 2.3 / Figure 4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaymentDTO:
    """
    Inbound payment payload boundary.
    Validates data before invoking the External Payment Gateway (SRS FR-11).
    """
    user_id:     int
    property_id: int
    amount:      float
    method:      str = "credit_card"
    card_token:  Optional[str] = None   # Tokenized card reference; never raw PAN

    VALID_METHODS = ("credit_card", "bank_transfer")

    def __post_init__(self):
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        if not isinstance(self.property_id, int) or self.property_id <= 0:
            raise ValueError("property_id must be a positive integer")
        if self.amount is None or float(self.amount) <= 0:
            raise ValueError("amount must be greater than zero")
        if self.method not in self.VALID_METHODS:
            raise ValueError(
                f"payment method must be one of {self.VALID_METHODS}"
            )

    def validate(self) -> bool:
        """Satisfies SDS class-diagram contract."""
        return True


@dataclass(frozen=True)
class ReceiptDTO:
    """
    Outbound payment receipt boundary.
    Maps persisted row data for the controller to prevent sensitive data leakage.
    """
    payment_id:     int
    reference:      str
    amount:         float
    property_id:    int
    property_title: str
    status:         str = "completed"

    def to_dict(self) -> dict:
        """Serializes the receipt for the API response."""
        return {
            "ok":             True,
            "payment_id":     self.payment_id,
            "reference":      self.reference,
            "amount":         self.amount,
            "property_id":    self.property_id,
            "property_title": self.property_title,
            "status":         self.status,
        }