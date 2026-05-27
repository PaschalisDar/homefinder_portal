"""
Admin Management Endpoints
--------------------------
SDS Reference: §4 Team Coordination and Contributions (Artifact ownership)
SRS Reference: §2.2 Requirements Classification (FR-10 / RE-12: Admin Management)

Description: Handles administrative routing for updating property listings,
managing user interactions, responding to inquiries, and modifying appointments.
"""

import logging
from flask import request, render_template, redirect, url_for, flash, g
from services import PropertyService
from repositories import UserRepository, AuditLogRepository
from models import decrypt_pii
from .utils import role_required, get_notifications

logger = logging.getLogger(__name__)

# Core system component dependencies (SDS §1)
prop_svc = PropertyService()
user_repo = UserRepository()
audit_repo = AuditLogRepository()

def register_admin_routes(app):
    
    # --- PROPERTY MANAGEMENT ENDPOINTS (SRS FR-10 / SDS §3.1) ---

    @app.route("/admin/properties/new", methods=["GET", "POST"])
    @role_required("admin")
    def admin_property_new():
        if request.method == "POST":
            files = request.files.getlist("property_images")
            # Delegates object creation logic to PropertyService pipeline
            result = prop_svc.create(request.form.to_dict(), g.user_id, files=files)
            flash(f"Property '{result['title']}' created.", "success")
            return redirect(url_for("dashboard"))
        return render_template("admin_property_form.html", prop=None, user=g.user, role=g.role, action="Create", notifs=get_notifications())

    @app.route("/admin/properties/edit/<int:pid>", methods=["GET", "POST"])
    @role_required("admin")
    def admin_property_edit(pid: int):
        prop = prop_svc.get(pid)
        if not prop:
            flash("Property not found.", "warning")
            return redirect(url_for("dashboard"))
        
        if request.method == "POST":
            delete_ids = request.form.getlist("delete_images")
            files = request.files.getlist("property_images")
            prop_svc.update(pid, request.form.to_dict(), g.user_id, files=files, delete_images=delete_ids)
            flash("Property updated.", "success")
            return redirect(url_for("dashboard"))
            
        return render_template("admin_property_form.html", prop=prop, user=g.user, role=g.role, action="Edit", notifs=get_notifications())

    @app.route("/admin/properties/delete/<int:pid>", methods=["POST"])
    @role_required("admin")
    def admin_property_delete(pid: int):
        prop_svc.delete(pid, g.user_id)
        flash("Property deleted.", "info")
        return redirect(url_for("dashboard"))

    # --- USER INQUIRY MANAGEMENT (SRS FR-07, FR-10) ---

    @app.route("/admin/inquiries", methods=["GET", "POST"])
    @role_required("admin")
    def admin_inquiries():
        if request.method == "POST":
            prop_svc.respond_inquiry(
                int(request.form["inquiry_id"]),
                request.form["response"],
                g.user_id,
            )
            flash("Response sent.", "success")
            return redirect(url_for("admin_inquiries"))
        inquiries = prop_svc.get_all_inquiries()
        return render_template("admin_inquiries.html", inquiries=inquiries, user=g.user, role=g.role, notifs=get_notifications())

    # --- APPOINTMENT CONCURRENCY MANAGEMENT (SRS FR-06 / SDS Table 1) ---

    @app.route("/admin/appointments")
    @role_required("admin")
    def admin_appointments():
        appointments = prop_svc.get_all_appointments()
        return render_template("admin_appointments.html", appointments=appointments, user=g.user, role=g.role, notifs=get_notifications())

    @app.route("/admin/appointments/<int:id>/update", methods=["POST"])
    @role_required("admin")
    def admin_appointment_update(id: int):
        status = request.form.get("status")
        logger.info("[ADMIN] appointment #%d update requested: status=%s by admin #%d", id, status, g.user_id)
        # Updates viewing appointment slots using concurrency locking guards
        result = prop_svc.update_appointment_status(id, status, g.user_id)
        if result["ok"]:
            flash(f"Appointment #{id} {status}.", "success")
        else:
            flash(result["error"], "danger")
        return redirect(url_for("admin_appointments"))

    # --- USER DATA & COMPLIANCE MANAGEMENT (SRS NFR-03 / SDS §2.1) ---

    @app.route("/admin/users")
    @role_required("admin")
    def admin_users():
        users = user_repo.get_all_users_with_stats()
        for u in users:
            if u.get("email_enc"):
                try: 
                    # Operationalizes GDPR compliance by decrypting PII isolated fields at runtime
                    u["email"] = decrypt_pii(u["email_enc"])
                except Exception: 
                    u["email"] = "Decryption error"
            else:
                u["email"] = "No email"
        return render_template("admin_users.html", users=users, user=g.user, role=g.role, notifs=get_notifications())

    @app.route("/admin/users/<int:id>/toggle", methods=["POST"])
    @role_required("admin")
    def admin_user_toggle(id: int):
        if id == g.user_id:
            flash("You cannot deactivate yourself.", "warning")
        else:
            user_repo.toggle_user_status(id)
            flash(f"User account #{id} status updated.", "info")
            # Enforces append-only security auditing footprint (SRS NFR-04 / SDS §2.1)
            audit_repo.log("user_status_toggle", g.user_id, f"Toggled status for user #{id}")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:id>/activity")
    @role_required("admin")
    def admin_user_activity(id: int):
        target_user = user_repo.find_by_id(id)
        if not target_user:
            flash("User not found.", "warning")
            return redirect(url_for("admin_users"))
        
        profile  = user_repo.find_profile(id)
        favs     = prop_svc.get_favorites(id)
        appts    = prop_svc.get_appointments(id)
        
        return render_template(
            "admin_user_activity.html",
            target_user=target_user, profile=profile,
            favorites=favs, appointments=appts,
            user=g.user, role=g.role,
            notifs=get_notifications()
        )