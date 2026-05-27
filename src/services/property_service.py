"""
services/property_service.py
Property listings management, favorites tracking, viewings scheduler, and inquiries pipeline.
Ref: SRS FR-03, FR-04, FR-05, FR-06, FR-07, FR-08, FR-10.
"""

import os
import logging
from typing import Optional
from werkzeug.utils import secure_filename

from models import decrypt_pii
from repositories import (
    UserRepository, PropertyRepository, PaymentRepository, AuditLogRepository,
    FavoriteRepository, AppointmentRepository, InquiryRepository,
    NotificationRepository, PropertyImageRepository, PriceAlertRepository
)
from factories import PropertyDTO, PropertyFactory
from .notification_service import NotificationService

logger = logging.getLogger(__name__)

class PropertyService:
    def __init__(self):
        self._props   = PropertyRepository()
        self._images  = PropertyImageRepository()
        self._favs    = FavoriteRepository()
        self._apts    = AppointmentRepository()
        self._notifs  = NotificationRepository()
        self._audit   = AuditLogRepository()
        self._users   = UserRepository()
        self._inqs    = InquiryRepository()
        self._alerts  = PriceAlertRepository()
        self._notif_svc = NotificationService()

    def process_property_creation(self, dto: PropertyDTO) -> "Property":
        # Delegates object construction to the factory based on DTO resolved type.
        # Ref: SDS §3.1 (Factory Method - Property Factory), SRS FR-03.
        dto.validate()
        prop_domain = PropertyFactory.create_property(dto)
        row = prop_domain.to_dict()
        if dto.resolved_type == "commercial" and getattr(dto, "office_spaces", None) is not None:
            row["office_spaces"] = dto.office_spaces
        pid = self._props.save(row)
        prop_domain.id = pid
        return prop_domain

    def create(self, data: dict, created_by: int, files: list = None) -> dict:
        # Administrator adds property listings. Ref: SRS FR-10, SRS UC-08.
        prop_type = data.get("type") or data.get("category") or "residential"
        prop_type = prop_type.lower().strip()
        if prop_type not in {"residential", "commercial", "rental"}:
            prop_type = "residential"
        data["type"]     = prop_type
        data["category"] = prop_type

        dto = PropertyDTO(
            title                 = data["title"],
            price                 = float(data["price"]),
            location              = data["location"],
            type                  = prop_type,
            description           = data.get("description"),
            bedrooms              = int(data["bedrooms"])  if data.get("bedrooms")  else None,
            bathrooms             = int(data["bathrooms"]) if data.get("bathrooms") else None,
            area_sqm              = float(data["area_sqm"]) if data.get("area_sqm") else None,
            has_garden            = data.get("has_garden") == "on",
            has_parking           = data.get("has_parking") == "on",
            lease_duration_months = int(data["lease_duration_months"]) if data.get("lease_duration_months") else None,
            security_deposit      = float(data["security_deposit"]) if data.get("security_deposit") else None,
            office_spaces         = int(data["office_spaces"]) if data.get("office_spaces") else None,
            owner_id              = created_by,
        )

        prop_domain = self.process_property_creation(dto)
        pid = prop_domain.id
        row = prop_domain.to_dict()

        if files:
            for i, f in enumerate(files):
                if f and self._allowed_file(f.filename):
                    filename = f"prop_{pid}_{i}_{secure_filename(f.filename)}"
                    path = os.path.join(os.path.dirname(__file__), "static", "uploads", "properties", filename)
                    f.save(path)
                    self._images.add(pid, filename, i)

        result = {**row, "id": pid}
        
        # Triggers notifications for similar listings matching alerts.
        # Ref: SRS FR-08, SRS UC-10.
        self.notify_similar_listing(result)
        self._audit.log("property_create", created_by, f"Property #{pid}: {dto.title}")
        return result

    def get(self, property_id: int) -> Optional[dict]:
        row = self._props.find_by_id(property_id)
        if not row:
            return None
        
        imgs = self._images.find_by_property(property_id)
        row["images"] = imgs
        if imgs:
            row["thumbnail"] = imgs[0]["image_path"]
            row["use_placeholder"] = False
        else:
            row["thumbnail"] = "no-image-available.jpg"
            row["use_placeholder"] = True
        
        row["status"] = "Available" if row.get("is_available") == 1 else ("Sold" if row.get("sold_at") else "Unavailable")
        try:
            # Applies Strategy pattern for tax calculations based on property type.
            # Ref: SDS §3.2 (Strategy - ITaxStrategy).
            prop_domain = PropertyFactory.from_db_row(row)
            row["tax_amount"]  = prop_domain.tax_amount()
            row["total_price"] = prop_domain.total_price()
            row["tax_label"]   = prop_domain.tax_label()
        except:
            pass
        return row

    def search(self, **kwargs) -> list[dict]:
        # Search and filter properties by specified criteria.
        # Ref: SRS FR-04, SRS UC-03.
        rows = self._props.search(**kwargs)
        for row in rows:
            imgs = self._images.find_by_property(row["id"])
            if imgs:
                row["thumbnail"] = imgs[0]["image_path"]
                row["use_placeholder"] = False
            else:
                row["thumbnail"] = "no-image-available.jpg"
                row["use_placeholder"] = True
            row["status"] = "Available" if row.get("is_available") == 1 else ("Sold" if row.get("sold_at") else "Unavailable")
            try:
                # Tax calculation via Strategy pattern. Ref: SDS §3.2.
                prop_domain = PropertyFactory.from_db_row(row)
                row["tax_amount"]  = prop_domain.tax_amount()
                row["total_price"] = prop_domain.total_price()
                row["tax_label"]   = prop_domain.tax_label()
            except:
                row["tax_amount"] = row["total_price"] = 0.0
                row["tax_label"]  = ""
        return rows

    def get_all(self, available_only: bool = False) -> list[dict]:
        rows = self._props.get_all(available_only)
        for row in rows:
            imgs = self._images.find_by_property(row["id"])
            if imgs:
                row["thumbnail"] = imgs[0]["image_path"]
                row["use_placeholder"] = False
            else:
                row["thumbnail"] = "no-image-available.jpg"
                row["use_placeholder"] = True
            row["status"] = "Available" if row.get("is_available") == 1 else ("Sold" if row.get("sold_at") else "Unavailable")
        return rows

    def update(self, property_id: int, data: dict, updated_by: int, files: list = None, delete_images: list = None):
        # Administrator updates property listings. Ref: SRS FR-10.
        current = self._props.find_by_id(property_id)
        was_available = current.get("is_available", 1) if current else 1

        prop_type = (data.get("type") or data.get("category") or "residential").lower().strip()
        if prop_type not in {"residential", "commercial", "rental"}:
            prop_type = "residential"
        data["type"]     = prop_type
        data["category"] = prop_type

        data["is_available"] = 1 if data.get("status") == "Available" else 0

        data["has_garden"]  = 1 if data.get("has_garden") == "on" else 0
        data["has_parking"] = 1 if data.get("has_parking") == "on" else 0
        data["office_spaces"] = int(data["office_spaces"]) if data.get("office_spaces") else None

        if data.get("lease_duration_months"):
            data["lease_duration_months"] = int(data["lease_duration_months"])
        else:
            data["lease_duration_months"] = None

        if data.get("security_deposit"):
            data["security_deposit"] = float(data["security_deposit"])
        else:
            data["security_deposit"] = None

        self._props.update(property_id, data)

        if delete_images:
            for img_id in delete_images:
                self._images.delete(int(img_id))

        if files:
            existing_imgs = self._images.find_by_property(property_id)
            start_idx = len(existing_imgs)
            for i, f in enumerate(files):
                if f and self._allowed_file(f.filename):
                    filename = f"prop_{property_id}_{start_idx + i}_{secure_filename(f.filename)}"
                    path = os.path.join(os.path.dirname(__file__), "static", "uploads", "properties", filename)
                    f.save(path)
                    self._images.add(property_id, filename, start_idx + i)

        if data.get("is_available") == 0:
            # Cancels pending viewings if status changes to unavailable. 
            # Ref: SRS UC-05 (Concurrency Control Note).
            self._apts.cancel_for_property(property_id)

        # Notify subscribed users if property transitions to available.
        # Ref: SRS FR-08, SRS UC-10.
        if data.get("is_available") == 1 and was_available != 1:
            title = data.get("title", "a listing")
            for sub in self._alerts.find_subscribers_for_property(property_id):
                self._notifs.create(
                    sub["user_id"],
                    "Property Now Available",
                    f"A property you subscribed to is now available: {title}. Check it out!",
                )
                self._alerts.unsubscribe(sub["user_id"], property_id)
                try:
                    profile = self._users.find_profile(sub["user_id"])
                    sub_email = profile.get("email") if profile else None
                    if sub_email:
                        self._notif_svc.send_email(
                            sub_email,
                            "Property Now Available — HomeFinder",
                            f"A property you subscribed to is now available: {title}. Log in to HomeFinder to view it.",
                        )
                except Exception as e:
                    logger.warning("Subscriber availability email failed: %s", e)

        self._audit.log("property_update", updated_by, f"Property #{property_id}")

    def delete(self, property_id: int, deleted_by: int):
        self._images.delete_by_property(property_id)
        self._props.delete(property_id)
        self._audit.log("property_delete", deleted_by, f"Property #{property_id}")

    def _allowed_file(self, filename: str) -> bool:
        return "." in filename and \
               filename.rsplit(".", 1)[1].lower() in {"jpg", "jpeg", "png", "webp"}

    def add_favorite(self, user_id: int, property_id: int):
        # User saves property to personal favorites. Ref: SRS FR-05, SRS UC-04.
        self._favs.add(user_id, property_id)

    def remove_favorite(self, user_id: int, property_id: int):
        self._favs.remove(user_id, property_id)

    def get_favorites(self, user_id: int) -> list[dict]:
        return self._favs.find_by_user(user_id)

    def is_favorite(self, user_id: int, property_id: int) -> bool:
        return self._favs.is_favorite(user_id, property_id)

    def subscribe_to_notifications(self, user_id: int, property_id: int) -> dict:
        # User subscribes to similar listing alerts. Ref: SRS FR-08, SRS UC-10.
        already = self._alerts.is_subscribed(user_id, property_id)
        if already:
            return {"ok": False, "error": "Already subscribed to this property."}
        self._alerts.subscribe(user_id, property_id)
        prop = self._props.find_by_id(property_id)
        self._notifs.create(
            user_id,
            "Subscription Confirmed",
            f"You will be notified when a similar '{prop['category']}' property becomes available.",
        )
        self._audit.log("subscribe_notification", user_id, f"Property #{property_id}")
        return {"ok": True}

    def unsubscribe_from_notifications(self, user_id: int, property_id: int) -> dict:
        self._alerts.unsubscribe(user_id, property_id)
        self._audit.log("unsubscribe_notification", user_id, f"Property #{property_id}")
        return {"ok": True}

    def get_subscriptions(self, user_id: int) -> list[dict]:
        return self._alerts.find_by_user(user_id)

    def notify_similar_listing(self, new_property: dict):
        # Triggers alerts for matching unavailable listings. Ref: SRS FR-08.
        category    = new_property.get("category", "")
        subscribers = self._alerts.find_by_category(category)
        for sub in subscribers:
            self._notifs.create(
                sub["user_id"],
                "New Similar Listing",
                f"A new '{category}' property matching your alert is now available: {new_property.get('title', '')}.",
            )
            try:
                if sub.get("email_enc"):
                    email = decrypt_pii(sub["email_enc"])
                    self._notif_svc.send_email(
                        email,
                        "New Similar Listing — HomeFinder",
                        f"A new '{category}' property matching your alert is now available: "
                        f"{new_property.get('title', '')}. Log in to HomeFinder to view it.",
                    )
            except Exception as e:
                logger.warning("New listing subscriber email failed for user #%d: %s", sub["user_id"], e)

    def schedule_viewing(self, user_id: int, property_id: int, scheduled_at: str, notes: str = "") -> dict:
        # Schedules property viewing and enforces concurrency control.
        # Ref: SRS FR-06, SRS UC-05.
        apt_id = self._apts.create(user_id, property_id, scheduled_at, notes)
        if not apt_id:
            return {"ok": False, "error": "This slot is no longer available. Please try a different time."}
        try:
            prop = self._props.find_by_id(property_id)
            self._notifs.create(user_id, "Viewing Scheduled", f"Your viewing for '{prop['title']}' at {scheduled_at} is pending confirmation.")
            user = self._users.find_by_id(user_id)
            username = user["username"] if user else f"User #{user_id}"
            for admin in self._users.find_all_admins():
                self._notifs.create(admin["id"], "New Viewing Request", f"User '{username}' requested a viewing for '{prop['title']}' on {scheduled_at}.")
                try:
                    admin_profile = self._users.find_profile(admin["id"])
                    admin_email = admin_profile.get("email") if admin_profile else None
                    if admin_email:
                        self._notif_svc.send_email(admin_email, "New Viewing Request — HomeFinder", f"User '{username}' requested a viewing for '{prop['title']}' on {scheduled_at}.")
                except Exception as e:
                    logger.warning("Admin viewing-request email failed: %s", e)
            self._audit.log("schedule_viewing", user_id, f"Property #{property_id} at {scheduled_at}")
            try:
                user = self._users.find_by_id(user_id)
                profile = self._users.find_profile(user_id)
                email = profile.get("email") if profile else None
                if email:
                    self._notif_svc.send_viewing_confirmation(email, prop["title"], scheduled_at, user["username"])
            except Exception as email_err:
                logger.warning("Optional email confirmation failed: %s", email_err)
            return {"ok": True, "id": apt_id}
        except Exception as e:
            logger.error("Post-scheduling tasks failed: %s", e)
            return {"ok": True, "id": apt_id, "warning": "Booking saved, but notification failed."}

    def get_appointments(self, user_id: int) -> list[dict]:
        return self._apts.find_by_user(user_id)

    def submit_inquiry(self, user_id: int, property_id: int, message: str) -> int:
        # Submit inquiries directly to specific listings. Ref: SRS FR-07, SRS UC-06.
        inq_id = self._inqs.create(user_id, property_id, message)
        try:
            prop = self._props.find_by_id(property_id)
            prop_title = prop["title"] if prop else f"Property #{property_id}"
            user = self._users.find_by_id(user_id)
            username = user["username"] if user else f"User #{user_id}"
            notif_msg = f"User '{username}' submitted an inquiry for '{prop_title}': {message[:120]}"
            for admin in self._users.find_all_admins():
                self._notifs.create(admin["id"], "New Inquiry Received", notif_msg)
                try:
                    admin_profile = self._users.find_profile(admin["id"])
                    admin_email = admin_profile.get("email") if admin_profile else None
                    if admin_email:
                        self._notif_svc.send_email(admin_email, "New Inquiry Received — HomeFinder", notif_msg)
                except Exception as e:
                    logger.warning("Admin inquiry email failed: %s", e)
        except Exception as e:
            logger.warning("Inquiry admin notification failed: %s", e)
        self._audit.log("inquiry_submit", user_id, f"Property #{property_id}")
        return inq_id

    def get_inquiries_for_user(self, user_id: int) -> list[dict]:
        return self._inqs.find_by_user(user_id)

    def get_all_inquiries(self) -> list[dict]:
        return self._inqs.get_all()

    def respond_inquiry(self, inquiry_id: int, response: str, admin_id: int):
        # Administrator manages user interactions. Ref: SRS FR-10, SRS UC-11.
        self._inqs.respond(inquiry_id, response)
        try:
            inquiry = self._inqs.find_by_id(inquiry_id)
            if inquiry:
                prop = self._props.find_by_id(inquiry["property_id"])
                prop_title = prop["title"] if prop else f"Property #{inquiry['property_id']}"
                notif_msg = f"Your inquiry for '{prop_title}' has been answered. Response: {response[:200]}"
                self._notifs.create(inquiry["user_id"], "Inquiry Response Received", notif_msg)
                try:
                    profile = self._users.find_profile(inquiry["user_id"])
                    user_email = profile.get("email") if profile else None
                    if user_email:
                        self._notif_svc.send_email(user_email, "Inquiry Response Received — HomeFinder", notif_msg)
                except Exception as e:
                    logger.warning("Inquiry response email failed: %s", e)
        except Exception as e:
            logger.error("[NOTIF] respond_inquiry notification FAILED for inquiry #%d: %s", inquiry_id, e, exc_info=True)
        self._audit.log("inquiry_respond", admin_id, f"Inquiry #{inquiry_id}")

    def stats(self) -> dict:
        return {
            "total":       self._props.count(),
            "by_category": self._props.count_by_category(),
        }

    def get_all_appointments(self) -> list[dict]:
        rows = self._apts.get_all_appointments()
        for r in rows:
            if r.get("email_enc"):
                try: r["email"] = decrypt_pii(r["email_enc"])
                except Exception: r["email"] = "Decryption failed"
            else:
                r["email"] = "No email"
        return rows

    def update_appointment_status(self, appt_id: int, status: str, admin_id: int) -> dict:
        # Enforces optimistic locking to prevent concurrent state overrides.
        # Ref: SDS §2.1 (ERD - APPOINTMENT entity optimistic locking).
        appt = self._apts._q("SELECT * FROM appointment WHERE id = ?", (appt_id,))
        if not appt:
            return {"ok": False, "error": "Appointment not found"}
        success = self._apts.update_status(appt_id, status, appt["version"])
        if not success:
            return {"ok": False, "error": "Concurrent update detected. Please refresh."}
        prop = self._props.find_by_id(appt["property_id"])
        prop_title = prop["title"] if prop else f"Property #{appt['property_id']}"
        msg = f"Your viewing for '{prop_title}' on {appt['scheduled_at']} has been {status} by the administrator."
        try:
            self._notifs.delete_for_user_by_title(appt["user_id"], "Viewing Scheduled")
        except Exception as e:
            logger.warning("[NOTIF] Could not delete stale notification: %s", e)
        try:
            self._notifs.create(appt["user_id"], "Viewing Update", msg)
        except Exception as e:
            logger.error("[NOTIF] FAILED to create notification for user #%d: %s", appt["user_id"], e, exc_info=True)
        try:
            profile = self._users.find_profile(appt["user_id"])
            user_email = profile.get("email") if profile else None
            if user_email:
                self._notif_svc.send_email(user_email, f"Viewing {status.capitalize()} — HomeFinder", msg)
        except Exception as e:
            logger.warning("[NOTIF] Email to user failed: %s", e)
        self._audit.log("appointment_status_update", admin_id, f"Appointment #{appt_id} set to {status}")
        return {"ok": True}