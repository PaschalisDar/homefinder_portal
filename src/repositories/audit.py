"""
Module: repositories.audit
Description: Handles persistence, analytical counting, and maintenance cycles for security audit logs.
References:
  - SRS RE-14 / NFR-04: Activity logs must be retained for a period of 3 months.
  - SDS §2.1: AUDIT_LOG table contains an append-only history with a 3-month TTL enforced on application startup.
  - SDS Table 2: Ownership matrix for AuditLogRepository tracking administrative/security events.
"""

from datetime import datetime, timedelta
from .base import BaseRepository

class AuditLogRepository(BaseRepository):
    
    def log(self, action: str, user_id: int = None, detail: str = "", ip_address: str = ""):
        """
        Appends a new security-relevant event entry into the authoritative audit trail.
        Ref: SDS §2.1 (AUDIT_LOG append-only mechanics).
        """
        self._exec(
            "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
            (user_id, action, detail, ip_address),
        )

    def recent_this_month(self) -> list[dict]:
        """
        Retrieves the operational log events generated within the current calendar month.
        Ref: SRS FR-09 / UC-09 (Supervisor search trend reporting and activity logs).
        """
        return self._q(
            """SELECT a.*, u.username 
               FROM audit_log a
               LEFT JOIN user u ON a.user_id = u.id
               WHERE a.created_at >= date('now', 'start of month')
               ORDER BY a.created_at DESC LIMIT 100""",
            many=True,
        )

    def purge_old(self) -> int:
        """
        Enforces data minimization rules by purging history rows older than 3 calendar months.
        Ref: SRS RE-14 / NFR-04 (3-month log retention SLA) | SDS §2.1 (Startup TTL cleanups).
        """
        from models import get_db
        cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            cur = conn.execute("DELETE FROM audit_log WHERE created_at < ?", (cutoff,))
            return cur.rowcount

    def count_actions(self, action: str) -> int:
        """
        Aggregates operational activity statistics to feed monthly trend reporting layers.
        Ref: SRS FR-09 (Supervisor reporting data source).
        """
        return self._q("SELECT COUNT(*) FROM audit_log WHERE action = ?", (action,), scalar=True) or 0