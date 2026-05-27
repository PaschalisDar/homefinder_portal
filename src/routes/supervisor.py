"""
Supervisor Reporting Endpoints
------------------------------
SDS Reference: §4 Team Coordination and Contributions
SRS Reference: §2.2 Requirements Classification (FR-09 / RE-11)

Description: Handles the generation and presentation of monthly analytics 
and search trends specifically for Customer Service Supervisors.
"""

from flask import render_template, g
from services import ReportService
from .utils import role_required, get_notifications

report_svc = ReportService()

def register_supervisor_routes(app):
    
    # --- SUPERVISOR ANALYTICS (SRS FR-09 / UC-09) ---
    
    @app.route("/supervisor/reports")
    @role_required("supervisor")
    def supervisor_reports():
        # Aggregates system metrics for managerial review
        report = report_svc.monthly_summary()
        return render_template(
            "supervisor_reports.html",
            report=report, user=g.user, role=g.role,
            notifs=get_notifications(),
        )