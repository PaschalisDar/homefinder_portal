"""
Routes Package Initialization
-----------------------------
SDS Reference: §1 Software Architecture (Modular Monolithic Architecture)
SRS Reference: §2.1 Requirements Elicitation (RE-1 to RE-16)

Description: Centralized route registration that maps decoupled down-stream 
service controllers into a single application runtime.
"""

from .auth import register_auth_routes
from .main import register_main_routes
from .properties import register_properties_routes
from .notifications import register_notifications_routes
from .admin import register_admin_routes
from .supervisor import register_supervisor_routes

def register_routes(app):
    # Register authentication and security routes (SDS §2.2 / SRS FR-01, FR-02)
    register_auth_routes(app)
    
    # Register core application logic and public landing routes
    register_main_routes(app)
    
    # Register property catalogue browsing and filtering routes (SDS §3.1, §3.2 / SRS FR-03, FR-04)
    register_properties_routes(app)
    
    # Register user notification and alert routing (SRS FR-08)
    register_notifications_routes(app)
    
    # Register administrative management operations (SRS FR-10)
    register_admin_routes(app)
    
    # Register supervisor analytics and business reporting routes (SRS FR-09)
    register_supervisor_routes(app)