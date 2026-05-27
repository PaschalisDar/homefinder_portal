"""
services/exceptions.py
Custom exceptions for the HomeFinder Portal.
"""

class RateLimitExceeded(Exception):
    """
    Raised when credential attempts exceed the limit.
    Ref: SDS §2.2.1 (Rate Limiting), SRS NFR-02 (Security).
    """
    http_status = 429


class PaymentDeclined(Exception):
    """
    Raised when the external payment gateway declines the transaction.
    Ref: SDS §2.3 (Transaction Processing), SRS FR-11.
    """
    http_status = 400


class ValidationError(Exception):
    """
    Raised on DTO validation failures (e.g., AuthDTO, PaymentDTO).
    Ref: SDS §2.2.2 (DTO Boundaries), SDS §2.3.
    """
    http_status = 400