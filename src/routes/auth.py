"""
Authentication & Access Control Endpoints
-----------------------------------------
SDS Reference: §2.2 Authentication & Security Flow
SRS Reference: §2.2 Requirements Classification (FR-01, FR-02, NFR-01, NFR-02, NFR-03)

Description: Handles identity lifecycle operations including secure user registration, 
two-phase TOTP login verification, secure session cookie containment, and logout.
"""

from flask import request, render_template, redirect, url_for, flash, session, g
from services import AuthService, RateLimitExceeded, ValidationError
from .utils import JWT_COOKIE_NAME, JWT_COOKIE_MAX_AGE

# Core authentication subsystem mapping back to AuthService component layout
auth_svc = AuthService()

def register_auth_routes(app):
    
    # --- USER REGISTRATION ENDPOINT (SRS FR-01 / NFR-03) ---

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if getattr(g, "user", None):
            return redirect(url_for("dashboard"))
        
        if request.method == "POST":
            form_data = request.form.to_dict()
            # Enforces explicit legal agreement to support data processing minimization guidelines
            gdpr = request.form.get("gdpr_consent") == "on"
            if not gdpr:
                flash("You must accept the privacy policy to register.", "warning")
                return render_template("register.html", form_data=form_data)
            
            if request.form.get("password") != request.form.get("confirm_password"):
                flash("Passwords do not match.", "warning")
                return render_template("register.html", form_data=form_data)

            # Invokes core operational storage layer mapping data directly to USER/USER_PROFILE tables
            result = auth_svc.register(
                username     = request.form.get("username", "").strip(),
                password     = request.form.get("password"),
                email        = request.form.get("email", "").strip().lower(),
                full_name    = request.form.get("full_name", "").strip(),
                gdpr_consent = gdpr,
            )
            
            if result["ok"]:
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for("login"))
            
            flash(result["error"], "danger")
            return render_template("register.html", form_data=form_data)
            
        return render_template("register.html", form_data=None)

    # --- TWO-PHASE LOGIN: PHASE 1 CREDENTIAL CHECK (SRS FR-02 / NFR-02) ---

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if getattr(g, "user", None):
            return redirect(url_for("dashboard"))
            
        if request.method == "POST":
            try:
                # Triggers standard dynamic sliding window counter via LoginAttemptRepository tracking
                result = auth_svc.initiate_login(
                    username = request.form["username"].strip(),
                    password = request.form["password"],
                    ip       = request.remote_addr,
                )
            except RateLimitExceeded as exc:
                # Hard block yielding a strict 429 payload modeling layout sequences
                flash(str(exc), "danger")
                return render_template("login.html"), 429
            except ValidationError as exc:
                # Returns 400 validation layout payload sequence structure mapping
                flash(str(exc), "danger")
                return render_template("login.html"), 400

            if result["ok"]:
                # Safe temporary cross-request state container assignment
                session["pre_auth_token"] = result["pre_auth_token"]
                return redirect(url_for("verify_2fa"))
            flash(result["error"], "danger")
        return render_template("login.html")

    # --- TWO-PHASE LOGIN: PHASE 2 TOTP VERIFICATION (SRS FR-02 / NFR-01 / NFR-02) ---

    @app.route("/verify-2fa", methods=["GET", "POST"])
    def verify_2fa():
        pre_token = session.get("pre_auth_token")
        if not pre_token:
            return redirect(url_for("login"))
            
        if request.method == "POST":
            token  = request.form.get("otp", "").strip()
            try:
                # Validates token payload and destroys temporal database entry to counteract replay attacks
                result = auth_svc.verify_2fa(pre_token, token, ip=request.remote_addr)
            except ValidationError as exc:
                flash(str(exc), "danger")
                return render_template("verify_2fa.html"), 400

            if result["ok"]:
                session.pop("pre_auth_token", None)
                flash(f"Welcome back, {result['username']}!", "success")
                resp = redirect(url_for("dashboard"))
                
                # Issues signed stateless authorization JWT using programmatic containment rules
                resp.set_cookie(
                    JWT_COOKIE_NAME,
                    value    = result["access_token"],
                    max_age  = JWT_COOKIE_MAX_AGE,
                    httponly = True,  # Counteracts DOM-based script token exfiltration attempts
                    secure   = True,  # Restricts packet delivery strictly over safe TLS connections
                    samesite = "Lax", # Mitigates Cross-Site Request Forgery attack vectors
                )
                return resp
            flash(result["error"], "danger")
        return render_template("verify_2fa.html")

    # --- SESSION DESTRUCTION ENDPOINT (SRS NFR-02) ---

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        resp = redirect(url_for("index"))
        # Revokes client authority footprint by deleting the state cookie container entirely
        resp.delete_cookie(JWT_COOKIE_NAME)
        return resp