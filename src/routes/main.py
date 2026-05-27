"""
Core Routing & Role-Based Dashboards
------------------------------------
SDS Reference: §1 Software Architecture (Modular Monolithic Application Runtime)
SRS Reference: §3.1 Actors and Usecases (AC-1, AC-2, AC-3)

Description: Central entry point routing and role-specific dashboard views 
for Users, Administrators, and Supervisors.
"""

from flask import render_template, g
from services import PropertyService, PaymentService, ReportService, NotificationService
from repositories import UserRepository, AuditLogRepository
from .utils import login_required, get_notifications

prop_svc = PropertyService()
pay_svc = PaymentService()
report_svc = ReportService()
notif_svc = NotificationService()
user_repo = UserRepository()
audit_repo = AuditLogRepository()

def register_main_routes(app):
    
    # --- PUBLIC LANDING PAGE (SRS FR-03) ---
    
    @app.route("/")
    def index():
        featured = prop_svc.get_all(available_only=True)[:6]
        return render_template("index.html", properties=featured, user=getattr(g, "user", None), role=getattr(g, "role", None))

    # --- ROLE-BASED DASHBOARD ROUTING (SRS FR-05, FR-09, FR-10) ---

    @app.route("/dashboard")
    @login_required
    def dashboard():
        if g.role == "admin":
            # Admin dashboard: System-wide property, inquiry, and user management (SRS FR-10)
            props        = prop_svc.get_all()
            inquiries    = prop_svc.get_all_inquiries()
            payments     = pay_svc.get_all_payments()
            appointments = prop_svc.get_all_appointments()
            users        = user_repo.get_all_users_with_stats()
            return render_template(
                "dashboard_admin.html",
                user=g.user, role=g.role,
                properties=props, inquiries=inquiries,
                payments=payments, appointments=appointments,
                users=users,
                notifs=get_notifications(),
            )
        elif g.role == "supervisor":
            # Supervisor dashboard: Monthly analytics and audit overview (SRS FR-09)
            report = report_svc.monthly_summary()
            audit  = audit_repo.recent_this_month()
            return render_template(
                "dashboard_supervisor.html",
                user=g.user, role=g.role,
                report=report, audit=audit, notifs=get_notifications(),
            )
        else:
            # User dashboard: Personal interactions, favorites, and payments (SRS FR-05, FR-06)
            favs    = prop_svc.get_favorites(g.user_id)
            apts    = prop_svc.get_appointments(g.user_id)
            pays    = pay_svc.get_user_payments(g.user_id)
            inqs    = prop_svc.get_inquiries_for_user(g.user_id)
            notifs  = notif_svc.get_for_user(g.user_id)
            subs    = prop_svc.get_subscriptions(g.user_id)
            profile = user_repo.find_profile(g.user_id)
            return render_template(
                "dashboard_user.html",
                user=g.user, role=g.role,
                favorites=favs, appointments=apts,
                payments=pays, inquiries=inqs, notifications=notifs,
                subscriptions=subs, profile=profile,
                notifs=get_notifications(),
            )