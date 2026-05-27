"""
Shared Routing Utilities & Decorators
-------------------------------------
SDS Reference: §2.2.4 Session Establishment (JWT configuration)
SRS Reference: §2.2 Requirements Classification (FR-02, NFR-02)

Description: Provides access control decorators and shared layout utilities 
to enforce security boundaries and role-based access.
"""

import functools
from flask import g, flash, redirect, url_for
from repositories import NotificationRepository

# JWT Cookie configuration bounds (SDS §2.2.4)
JWT_COOKIE_NAME = "hf_access"
JWT_COOKIE_MAX_AGE = 24 * 60 * 60

notif_repo = NotificationRepository()

def get_notifications():
    """Fetches unread notifications for global layout rendering."""
    if getattr(g, "user_id", None):
        return notif_repo.find_by_user(g.user_id, unread_only=True)
    return []

def login_required(f):
    """
    Base authentication guard.
    Enforces active session presence before allowing route execution (SRS NFR-02).
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not getattr(g, "user", None):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    """
    Role-based authorization guard.
    Restricts access to specified actor roles (SRS AC-1, AC-2, AC-3).
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            if not getattr(g, "user", None):
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if getattr(g, "role", None) not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return decorator