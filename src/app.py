"""
app.py — HomeFinder Portal
Flask application factory, JWT middleware, rate limiting, and core configurations.

References:
- SDS Section 1: API Gateway & Application Runtime.
- SDS Section 2.2.4: Session Establishment (JWT & HttpOnly cookies).
- SRS NFR-04 / RE-14: Audit log retention.
- SRS NFR-05 / RE-15: Maintenance mode downtime.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from flask import Flask, request, session, g, render_template

from models import init_db, MAINTENANCE_MODE
from services import AuthService
from repositories import AuditLogRepository, UserRepository, Pending2FARepository, LoginAttemptRepository
from routes.utils import JWT_COOKIE_NAME
from routes import register_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.secret_key = os.environ.get("HF_SECRET_KEY", "homefinder-dev-secret-change-in-prod")

    # Secure cookie configuration (SDS Section 2.2.4)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"]   = os.environ.get("HF_SECURE_COOKIES", "0") == "1"

    with app.app_context():
        init_db()
        
        # Enforce 3-month audit log retention on startup (SRS NFR-04, RE-14)
        try:
            purged_audit = AuditLogRepository().purge_old()
            if purged_audit:
                logger.info("[STARTUP] Purged %d audit_log rows older than 3 months", purged_audit)
        except Exception as exc:
            logger.warning("[STARTUP] Audit purge skipped: %s", exc)
            
        # Cleanup expired 2FA tokens and rate-limit logs (SDS Section 2.2.1 & 2.2.3)
        try:
            Pending2FARepository().purge_expired()
            LoginAttemptRepository().purge_old()
        except Exception as exc:
            logger.warning("[STARTUP] Auth cleanup skipped: %s", exc)
            
        _seed_demo_data()

    user_repo = UserRepository()

    @app.before_request
    def maintenance_check():
        """Enforces the scheduled weekly 30-min downtime (SRS NFR-05, RE-15)."""
        if MAINTENANCE_MODE and request.endpoint not in ("static",):
            return render_template(
                "error.html", code=503,
                message="The system is currently undergoing scheduled maintenance (up to 30 minutes). Please try again shortly.",
                user=None, role=None,
            ), 503

    @app.before_request
    def load_user():
        """Authenticates requests via JWT from HttpOnly cookie (SDS Section 2.2.4)."""
        g.user    = None
        g.user_id = None
        g.role    = None
        
        token = request.cookies.get(JWT_COOKIE_NAME)
        if not token:
            token = session.get("access_token")
            
        if token:
            claims = AuthService.decode_token(token)
            if claims and claims.get("phase") != "pre_auth":
                g.user_id = int(claims.get("sub")) if claims.get("sub") else None
                g.role    = claims.get("role")
                if g.user_id:
                    u = user_repo.find_by_id(g.user_id)
                    # Single active session enforcement check
                    if u and u.get("is_active"):
                        g.user = u
                    else:
                        session.clear()
                        g.user_id = None
                        g.role = None
                        g.user = None

    # Register all routes from separated modules
    register_routes(app)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found.", user=getattr(g, "user", None), role=getattr(g, "role", None)), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="Access denied.", user=getattr(g, "user", None), role=getattr(g, "role", None)), 403

    @app.errorhandler(500)
    def server_error(e):
        logger.error("Internal Server Error: %s", e, exc_info=True)
        return render_template("error.html", code=500, message="Internal server error.", user=getattr(g, "user", None), role=getattr(g, "role", None)), 500

    @app.template_filter("currency")
    def currency_filter(value):
        try:
            return f"€{float(value):,.2f}"
        except (ValueError, TypeError):
            return value

    @app.context_processor
    def inject_now():
        return {"now": datetime.now(timezone.utc)}

    return app

def _seed_demo_data():
    """Create demo accounts and sample properties on first run to populate the MVP."""
    from services import AuthService, PropertyService
    from repositories import PropertyImageRepository, UserRepository
    from models import get_db

    upload_dir = os.path.join(os.path.dirname(__file__), "static", "uploads", "properties")
    os.makedirs(upload_dir, exist_ok=True)

    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM user").fetchone()[0]
    if count > 0:
        return

    auth_svc = AuthService()
    prop_svc = PropertyService()
    img_repo = PropertyImageRepository()

    # Pre-populate specific roles (SRS RE-11, RE-12)
    auth_svc.register("admin",      "Admin1234!",  "admin@homefinder.demo", "Admin User",      gdpr_consent=True, role="admin")
    auth_svc.register("supervisor", "Super5678!",  "supervisor@homefinder.demo", "Supervisor User", gdpr_consent=True, role="supervisor")
    auth_svc.register("user",       "User9012!",   "user@homefinder.demo", "Demo User",       gdpr_consent=True, role="user")

    user_repo = UserRepository()
    admin     = user_repo.find_by_username("admin")
    admin_id  = admin["id"] if admin else 1

    def _register_local_images(pid: int) -> None:
        try:
            prefix = f"prop_{pid}_"
            matches = sorted(f for f in os.listdir(upload_dir) if f.startswith(prefix) and f.lower().endswith(".jpg"))
            for order, filename in enumerate(matches):
                img_repo.add(pid, filename, order)
                logger.info("[SEED] Registered image: %s (property #%d)", filename, pid)
        except Exception as img_err:
            logger.warning("[SEED] Image registration skipped for property #%d: %s", pid, img_err)

    # Initial properties matching SRS categories (Residential, Commercial, Rental)
    sample_props = [
        {"title": "Breathtaking Modern 2-Bedroom Retreat with Panoramic Sea Views in Panorama",        "price": 495000, "location": "Panorama, Thessaloniki", "type": "residential", "category": "residential", "bedrooms": 2, "bathrooms": 2, "area_sqm": 183, "description": "A stunning, newly built 115 sq.m. home that perfectly blends contemporary luxury with breathtaking, unobstructed views of the Thermaikos Gulf. Interior Highlights Living & Kitchen: Sun-drenched, open-plan living area with premium wooden flooring, floor-to-ceiling glass doors, and a state-of-the-art minimalist white kitchen with a center island. Bedrooms: Two serene bedrooms, including a master suite with a private sea-view balcony and a spacious twin room overlooking the lush backyard. Bathroom: A sleek, spa-inspired bathroom with a large walk-in glass shower and elegant stone tiles. Outdoor Oasis Beautifully landscaped garden featuring mature olive trees, natural stone details, and clean architectural lines. Private parking space right at your doorstep. Experience the perfect mix of high-end modern living and Mediterranean tranquility."},
        {"title": "The City Loft",         "price": 325000, "location": "City Center, Thessaloniki", "type": "residential", "category": "residential", "bedrooms": 1, "bathrooms": 1, "area_sqm": 112, "description": "Step into this stunning converted factory loft that perfectly blends raw industrial charm with modern luxury. Boasting soaring high ceilings, exposed original brick walls, and heavy wooden beams, this open-concept sanctuary offers a truly unique living experience. It features polished concrete floors, a sleek modern kitchen with high-end appliances, a spectacular spa-inspired bathroom with a freestanding black tub, and a cozy mezzanine bedroom overlooking the spacious, light-filled living area."},
        {"title": "Pre-Sale: Ultra-Luxury Apartment at Riviera Tower (The Ellinikon)", "price": 1_200_000, "location": "The Ellinikon, Athens", "type": "residential", "category": "residential", "bedrooms": 1, "bathrooms": 1, "area_sqm": 157, "description": "Secure your piece of the Athenian Riviera before completion. This premium, off-plan apartment (approx. 130–160 sq.m.) at the iconic Riviera Tower blends minimalist luxury with a spectacular 'wow-factor' panoramic view of the Aegean Sea, the marina, and the coastal park. Key Highlights: Living & Dining: Bright, open-plan space with light marble floors, floor-to-ceiling glass doors, and an elegant kitchen featuring a Calacatta marble island. Master Suite: A serene sanctuary with natural textures, a walk-in closet, and a spa-like bathroom with a free-standing tub facing the sea. Flexible Space: A sophisticated home office/library with dark wood built-ins and direct balcony access. ⚠️ Important Investment Note (Off-Plan Sale) This property is currently under construction and is scheduled for completion in 2 years. It is being sold now (pre-sale), offering an exceptional early-entry price and a prime investment opportunity in Europe’s largest urban regeneration project before final delivery."},
        {"title": "Iconic Neoclassical Retail Space in Thessaloniki Center", "price": 780_000, "location": "City Center, Thessaloniki", "type": "commercial", "category": "commercial", "office_spaces": 1, "bathrooms": 1, "area_sqm": 174, "description": "A rare opportunity to lease an exquisite, neoclassical commercial space in the heart of Thessaloniki’s premium retail district. This completely vacant, move-in-ready property features a striking architectural interior with elegant minimalist arches, premium terrazzo flooring, and expansive floor-to-ceiling glass storefronts designed for maximum brand visibility. Perfectly lit with warm, sophisticated ambient lighting, this pristine layout offers a flawless blank canvas for a luxury boutique, flagship store, or high-end showroom looking to make an iconic statement."},
        {"title": "Sunlit Modern 2-Bedroom Apartment",   "price": 2_200,  "location": "Kalamaria, Thessaloniki", "type": "rental", "category": "rental", "bedrooms": 2, "bathrooms": 2, "area_sqm": 98, "description": "Discover your new home in the heart of Kalamaria. This ultra-modern, sun-drenched 3rd-floor apartment (98 sq.m.) offers the perfect blend of luxury and functionality. It features an impressively large living room with massive sliding glass doors, a modern kitchen with wooden countertops, two bedrooms (including one master with an en-suite bathroom), and a second sleek guest bathroom. With wooden flooring throughout and large balconies offering views, this is a rare opportunity in one of Thessaloniki's most premium areas, located just steps away from the shopping district and the beach."},
        {"title": "Piraeus Harbor Studio", "price": 800,  "location": "Piraeus, Athens", "type": "rental", "category": "rental", "bedrooms": 1, "bathrooms": 1, "area_sqm": 38, "description": "Experience the ultimate Mediterranean lifestyle in this bright, sun-drenched apartment. Located just steps away from the sparkling sea, this elegant home features classic white marble floors, a clean minimalist aesthetic, and expansive sliding glass doors that seamlessly connect the indoor living space to a large private balcony. Complete with a fully equipped modern kitchen and a tranquil, courtyard-facing bedroom, this seaside haven offers the perfect balance of luxury and relaxation."},
        {"title": "Iconic Business Space with Lycabettus Hill View", "price": 900_000,  "location": "Kolonaki, Athens", "type": "commercial", "category": "commercial", "office_spaces": 3, "bathrooms": 1, "area_sqm": 457, "description": "An impressive, high-ceiling co-working space in the heart of Athens. Offering spectacular panoramic views of Lycabettus Hill, ample natural light from large floor-to-ceiling windows, modern design with biophilic elements (green wall), and flexible work zones (ranging from private focus pods to large communal tables). Ideal for innovative teams seeking an inspirational environment."},
        {"title": "Modern Minimalist Detached House with Mediterranean Charm", "price": 1_700, "location": "Naoussa, Paros, Greece", "type": "rental", "category": "rental", "bedrooms": 2, "bathrooms": 1, "area_sqm": 90, "description": "A beautiful detached home blending classic Greek countryside charm with contemporary design. Featuring clean lines, white-washed walls, and abundant natural light, this property is the definition of 'less is more.' Interior Living & Dining: Spacious living room with a cozy corner sofa and a fully equipped minimalist kitchen. Bedrooms: Two bright, serene bedrooms designed for ultimate relaxation. Aesthetics: Large-format premium grey tiles combined with light oak wood furniture for a cool, luxurious feel. Outdoor & Extras Private, stone-paved courtyard with an olive tree and lavender. Private parking space for complete autonomy. Perfect for anyone seeking comfort, privacy, and elegant modern living."},
    ]
    for p in sample_props:
        p["owner_id"] = admin_id
        try:
            result = prop_svc.create(p, admin_id)
            _register_local_images(result["id"])
        except Exception as e:
            logger.warning("Seed property skip: %s", e)

    print("[SEED] Demo data created.")

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)