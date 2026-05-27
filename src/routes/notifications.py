"""
In-App Notification Endpoints
-----------------------------
SDS Reference: §2.3 Transaction Processing (Side effects implementation)
SRS Reference: §2.2 Requirements Classification (FR-08 / RE-10)

Description: Endpoints for managing real-time user notifications and read statuses.
"""

from flask import jsonify, g
from services import NotificationService
from repositories import NotificationRepository
from .utils import login_required

notif_svc = NotificationService()
notif_repo = NotificationRepository()

def register_notifications_routes(app):
    
    # --- NOTIFICATION STATE MANAGEMENT ---
    
    @app.route("/notifications/mark-read", methods=["POST"])
    @login_required
    def notifications_mark_read():
        notif_svc.mark_read(g.user_id)
        return jsonify({"ok": True})

    @app.route("/notifications/unread-count", methods=["GET"])
    @login_required
    def notifications_unread_count():
        count = notif_repo.unread_count(g.user_id)
        return jsonify({"count": count})

    @app.route("/notifications/list", methods=["GET"])
    @login_required
    def notifications_list():
        notifs = notif_repo.find_by_user(g.user_id, unread_only=False)
        for n in notifs:
            if hasattr(n.get("created_at"), "isoformat"):
                n["created_at"] = n["created_at"].isoformat()
        return jsonify(notifs)