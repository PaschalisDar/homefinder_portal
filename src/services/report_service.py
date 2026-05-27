"""
services/report_service.py
Metrics reporting engine for Customer Service Supervisors.
Ref: SRS FR-09, SRS UC-09 (View Reports).
"""

from repositories import PaymentRepository, PropertyRepository, AuditLogRepository, InquiryRepository, AppointmentRepository

class ReportService:
    def __init__(self):
        self._payments = PaymentRepository()
        self._props    = PropertyRepository()
        self._audit    = AuditLogRepository()
        self._inqs     = InquiryRepository()
        self._apts     = AppointmentRepository()

    def monthly_summary(self) -> dict:
        # Generates monthly analytics on trends and user activity.
        # Ref: SRS RE-11, SRS AC-3 (Customer Service Supervisor).
        by_cat = self._props.count_by_category()
        total_props = self._props.count()
        
        # Retrieves recent audit logs respecting the 3-month retention policy.
        # Ref: SRS NFR-04, SRS RE-14.
        recent_logs = self._audit.recent_this_month()
        
        return {
            "total_revenue":          self._payments.total_revenue(),
            "total_properties":       total_props,
            "by_category":            by_cat,
            "properties_by_category": by_cat,
            "open_inquiries":         self._inqs.count_open(),
            "total_inquiries":        len(self._inqs.get_all()),
            "recent_audit":           recent_logs,
            "recent_logs":            recent_logs,
            "all_payments":           self._payments.get_all(),
            "total_logins":           self._audit.count_actions("login_success"),
            "total_searches":         self._audit.count_actions("property_search"),
            "total_viewings":         len(self._apts.get_all_appointments()),
        }