"""
services/__init__.py
Initializes the services package and exports core service components.
Implements the Modular Monolithic Architecture defined in SDS §1.
"""

from .exceptions import RateLimitExceeded, PaymentDeclined, ValidationError
from .auth_service import AuthService
from .property_service import PropertyService
from .payment_service import PaymentService, ExternalPaymentGateway
from .notification_service import NotificationService
from .report_service import ReportService