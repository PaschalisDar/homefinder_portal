"""
Module: repositories
Description: Initialization of the repositories package. Manages access to the 
             persistence layer via data access aggregates.
References:
  - SDS §1.1: Repository-per-aggregate pattern (11 concrete repositories).
  - SDS Table 1: ERD Entity-to-Requirement Traceability Matrix.
"""

# Base repository helper
from .base import BaseRepository

# Core User & Security repositories (Ref: SRS FR-01, FR-02 | SDS §2.1, §2.2)
from .user import UserRepository
from .session import SessionRepository
from .auth_utils import Pending2FARepository, LoginAttemptRepository

# Property Domain repositories (Ref: SRS FR-03, FR-04, FR-05, FR-06, FR-07 | SDS §2.1)
from .property import PropertyRepository
from .favorite import FavoriteRepository
from .appointment import AppointmentRepository
from .inquiry import InquiryRepository
from .property_image import PropertyImageRepository
from .price_alert import PriceAlertRepository

# Payment processing repository (Ref: SRS FR-11 | SDS §2.3)
from .payment import PaymentRepository

# System Operations & Audit repositories (Ref: SRS RE-14 / NFR-04 | SDS §2.1)
from .audit import AuditLogRepository
from .notification import NotificationRepository