"""
Property Interaction & Transaction Endpoints
------------------------------------------
SDS Reference: §2.3 Transaction Processing (Payment Flow), §3.1 Factory Method
SRS Reference: §2.2 Requirements Classification (FR-03, FR-04, FR-05, FR-06, FR-07, FR-08, FR-11)

Description: Handles public property listings, advanced filtering, user interactions 
(favorites, viewings, inquiries), and ACID-compliant secure payments.
"""

import datetime
from flask import request, render_template, redirect, url_for, flash, g
from services import PropertyService, PaymentService, PaymentDeclined, ValidationError
from repositories import AuditLogRepository
from .utils import login_required, get_notifications

# Core service instantiations (SDS §1)
prop_svc = PropertyService()
pay_svc = PaymentService()
audit_repo = AuditLogRepository()

def register_properties_routes(app):
    
    # --- PROPERTY BROWSING & FILTERING (SRS FR-03, FR-04) ---
    
    @app.route("/properties")
    def properties():
        keyword      = request.args.get("keyword",  "")
        category     = request.args.get("category", "")
        location     = request.args.get("location", "")
        min_price    = float(request.args.get("min_price", 0) or 0)
        max_price    = float(request.args.get("max_price", 0) or 0)
        min_bedrooms = int(request.args.get("min_bedrooms", 0) or 0)

        # Delegates search and dynamic filtering to the PropertyService layer
        props = prop_svc.search(
            keyword      = keyword,
            category     = category,
            location     = location,
            min_price    = min_price,
            max_price    = max_price if max_price > 0 else 1e12,
            min_bedrooms = min_bedrooms,
        )

        if getattr(g, "user_id", None):
            parts = []
            if keyword:  parts.append(f"keyword='{keyword}'")
            if category: parts.append(f"category='{category}'")
            if location: parts.append(f"location='{location}'")
            detail = ", ".join(parts) if parts else "browsed all"
            # Records user search patterns for audit and supervisor reporting (SRS FR-09)
            audit_repo.log("property_search", g.user_id, detail)
        
        filters = {
            "keyword":      keyword,
            "category":     category,
            "location":     location,
            "min_price":    min_price if min_price else "",
            "max_price":    max_price if max_price else "",
            "min_bedrooms": min_bedrooms if min_bedrooms else "",
        }
        return render_template(
            "properties.html",
            properties = props,
            user       = getattr(g, "user", None),
            role       = getattr(g, "role", None),
            filters    = filters,
            notifs     = get_notifications(),
        )

    # --- PROPERTY DETAILS & STATUS ---

    @app.route("/properties/<int:pid>")
    def property_detail(pid: int):
        prop = prop_svc.get(pid)
        if not prop:
            flash("Property not found.", "warning")
            return redirect(url_for("properties"))
        
        is_fav = False
        is_subscribed = False
        if getattr(g, "user_id", None):
            is_fav = prop_svc.is_favorite(g.user_id, pid)
            is_subscribed = prop_svc._alerts.is_subscribed(g.user_id, pid)
            
        return render_template(
            "property_detail.html",
            prop          = prop,
            is_fav        = is_fav,
            is_subscribed = is_subscribed,
            user          = getattr(g, "user", None),
            role          = getattr(g, "role", None),
            notifs        = get_notifications(),
        )

    # --- FAVORITES MANAGEMENT (SRS FR-05) ---

    @app.route("/favorites/add/<int:pid>", methods=["GET", "POST"])
    @login_required
    def add_favorite(pid: int):
        prop_svc.add_favorite(g.user_id, pid)
        flash("Added to favourites.", "success")
        return redirect(request.referrer or url_for("properties"))

    @app.route("/favorites/remove/<int:pid>", methods=["GET", "POST"])
    @login_required
    def remove_favorite(pid: int):
        prop_svc.remove_favorite(g.user_id, pid)
        flash("Removed from favourites.", "info")
        return redirect(request.referrer or url_for("dashboard"))

    # --- NOTIFICATION SUBSCRIPTIONS (SRS FR-08) ---

    @app.route("/subscribe/<int:pid>", methods=["POST"])
    @login_required
    def subscribe_notifications(pid: int):
        result = prop_svc.subscribe_to_notifications(g.user_id, pid)
        if result["ok"]:
            flash("You will be notified when a similar property becomes available.", "success")
        else:
            flash(result.get("error", "Could not subscribe."), "warning")
        return redirect(request.referrer or url_for("properties"))

    @app.route("/unsubscribe/<int:pid>", methods=["POST"])
    @login_required
    def unsubscribe_notifications(pid: int):
        prop_svc.unsubscribe_from_notifications(g.user_id, pid)
        flash("Subscription removed.", "info")
        return redirect(request.referrer or url_for("dashboard"))

    # --- VIEWING SCHEDULING (SRS FR-06) ---

    @app.route("/schedule-viewing/<int:pid>", methods=["GET", "POST"])
    @login_required
    def schedule_viewing(pid: int):
        prop = prop_svc.get(pid)
        if not prop:
            flash("Property not found.", "warning")
            return redirect(url_for("properties"))
        if request.method == "POST":
            res = prop_svc.schedule_viewing(
                user_id      = g.user_id,
                property_id  = pid,
                scheduled_at = request.form["scheduled_at"],
                notes        = request.form.get("notes", ""),
            )
            if res.get("ok"):
                flash("Viewing scheduled successfully!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash(res.get("error", "Failed to schedule viewing."), "danger")

        # Generates upcoming calendar slots dynamically
        slots = []
        now = datetime.datetime.now()
        for i in range(1, 4):
            day = now + datetime.timedelta(days=i)
            for hour in [10, 14, 16]:
                dt = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                slots.append(dt.strftime("%Y-%m-%d %H:%M"))

        return render_template("schedule_viewing.html", prop=prop, slots=slots, user=g.user, role=g.role, notifs=get_notifications())

    # --- INQUIRY SUBMISSION (SRS FR-07) ---

    @app.route("/inquiry/<int:pid>", methods=["GET", "POST"])
    @login_required
    def inquiry(pid: int):
        prop = prop_svc.get(pid)
        if not prop:
            flash("Property not found.", "warning")
            return redirect(url_for("properties"))
        if request.method == "POST":
            prop_svc.submit_inquiry(g.user_id, pid, request.form["message"])
            flash("Inquiry submitted.", "success")
            return redirect(url_for("dashboard"))
        return render_template("inquiry.html", prop=prop, user=g.user, role=g.role, notifs=get_notifications())

    # --- SECURE PAYMENT PROCESSING (SRS FR-11 / SDS §2.3) ---

    @app.route("/payment/<int:pid>", methods=["GET", "POST"])
    @login_required
    def payment(pid: int):
        prop = prop_svc.get(pid)
        if not prop:
            flash("Property not found.", "warning")
            return redirect(url_for("properties"))
        if request.method == "POST":
            try:
                # Executes strict validation and transaction pipeline mapped in SDS Figure 4
                result = pay_svc.process(
                    user_id     = g.user_id,
                    property_id = pid,
                    amount      = prop["total_price"],
                    method      = request.form.get("method", "credit_card")
                )
            except PaymentDeclined as exc:
                # Maps external gateway failures to HTTP 400 Bad Request flows
                flash(f"Payment failed: {exc}", "danger")
                return render_template("payment.html", prop=prop, user=g.user, role=g.role, notifs=get_notifications()), 400
            except ValidationError as exc:
                # Handles strict DTO boundary validation failures (SDS §2.3)
                flash(f"Invalid payment data: {exc}", "danger")
                return render_template("payment.html", prop=prop, user=g.user, role=g.role, notifs=get_notifications()), 400

            if result["ok"]:
                flash(f"Payment successful! Reference: {result['reference']}", "success")
                return redirect(url_for("dashboard"))
            flash(f"Payment failed: {result['error']}", "danger")
        return render_template("payment.html", prop=prop, user=g.user, role=g.role, notifs=get_notifications())