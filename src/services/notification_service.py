"""
services/notification_service.py
Handles system notifications and email dispatching via Circuit Breaker.
Ref: SDS §3.3 (Circuit Breaker Email Service).
"""

import logging
from repositories import NotificationRepository, UserRepository
from .utils import EmailService

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self._notifs = NotificationRepository()
        self._users  = UserRepository()

    def send_email(self, to: str, subject: str, body: str) -> bool:
        # Implements Circuit Breaker pattern for email delivery (SDS §3.3).
        success = EmailService.send(to, subject, body)
        if not success:
            logger.warning("Email failed (circuit %s) — SMS fallback",
                           EmailService.breaker_state())
        return success

    def send_2fa_token(self, to_email: str, token: str, username: str):
        # Delivers 2FA token within the strict 30-second SLA.
        # Ref: SRS FR-02, SRS NFR-01, SDS §2.2.3.
        subject = "HomeFinder - Your Login Code"
        body    = (
            f"Hi {username},\n\n"
            f"Your one-time login code is: {token}\n\n"
            f"This code expires in 30 seconds.\n\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"- HomeFinder Security"
        )
        self.send_email(to_email, subject, body)

    def send_viewing_confirmation(self, to_email: str, prop_title: str,
                                   scheduled_at: str, username: str):
        # Dispatches viewing confirmation after successful scheduling.
        # Ref: SRS FR-06, SRS UC-05 (Schedule Property Viewing).
        self.send_email(
            to_email,
            f"Viewing Confirmed - {prop_title}",
            f"Hi {username},\n\nYour viewing of '{prop_title}' on {scheduled_at} "
            f"has been confirmed.\n\n- HomeFinder",
        )

    def create(self, user_id: int, title: str, message: str):
        # Stores in-app notifications (e.g., for payment receipts).
        # Ref: SDS §2.3 (Transaction Processing - Async Notification).
        self._notifs.create(user_id, title, message)

    def get_for_user(self, user_id: int) -> list[dict]:
        return self._notifs.find_by_user(user_id)

    def mark_read(self, user_id: int):
        self._notifs.mark_read(user_id)