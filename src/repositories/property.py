"""
Module: repositories.property
Description: Handles core catalog persistence, indexing queries, and taxonomy updates.
References:
  - SRS FR-03 / FR-04: Browse properties by category and filter by location, price range, and amenities.
  - SDS §1.1 / §2.1 Table 1: B-Tree index structures on price/location parameters; domain patterns mapping.
  - SDS §3.1 / §3.2: Supports Factory Method (PropertyFactory) subclasses and polymorphic Strategy mappings.
"""

from .base import BaseRepository

class PropertyRepository(BaseRepository):
    
    def save(self, data: dict) -> int:
        """
        Registers a new classified property row matching domain aggregate schema inputs.
        Ref: SRS FR-10 / UC-08 (Manage Listings) | SDS §3.1 (PropertyFactory translation context).
        """
        return self._exec(
            """INSERT INTO property
               (title, description, price, location, category, bedrooms, bathrooms, area_sqm,
                has_garden, has_parking, office_spaces, lease_duration_months, security_deposit, owner_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["title"], data.get("description"), data["price"], data["location"], data["category"],
                data.get("bedrooms"), data.get("bathrooms"), data.get("area_sqm"), data.get("has_garden"),
                data.get("has_parking"), data.get("office_spaces"), data.get("lease_duration_months"),
                data.get("security_deposit"), data["owner_id"]
            )
        )

    def find_by_id(self, prop_id: int) -> dict | None:
        """
        Queries a single unified domain listing entry using its primary index reference key.
        """
        return self._q("SELECT * FROM property WHERE id = ?", (prop_id,))

    def search(self, keyword="", category="", location="", min_price=0.0, max_price=1e12, min_bedrooms=0) -> list[dict]:
        """
        Executes granular user filtering matrices leveraging multi-column parameter parameters.
        Ref: SRS FR-04 / UC-03 | SDS Table 1 (B-Tree schema search optimizations for price and location filters).
        """
        sql = "SELECT * FROM property WHERE price BETWEEN ? AND ?"
        params = [min_price, max_price]
        if keyword:
            sql += " AND (title LIKE ? OR description LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if category:
            sql += " AND category = ?"
            params.append(category)
        if location:
            sql += " AND location LIKE ?"
            params.append(f"%{location}%")
        if min_bedrooms:
            sql += " AND bedrooms >= ?"
            params.append(min_bedrooms)
        sql += " ORDER BY is_available DESC, created_at DESC"
        return self._q(sql, tuple(params), many=True)

    def get_all(self, available_only: bool = False) -> list[dict]:
        """
        Fetches baseline listing collections for administrative index dashboards or public views.
        Ref: SRS FR-03 (Categorized property catalog discovery structures).
        """
        if available_only:
            return self._q("SELECT * FROM property WHERE is_available = 1 ORDER BY created_at DESC", many=True)
        return self._q("SELECT * FROM property ORDER BY created_at DESC", many=True)

    def count(self) -> int:
        """
        Gathers general metrics mapping complete structural counts for supervisor trend sheets.
        """
        return self._q("SELECT COUNT(*) FROM property", scalar=True) or 0

    def count_by_category(self) -> dict:
        """
        Groups catalog totals matching operational market sectors.
        Ref: SRS FR-09 (Supervisor analytical reporting data context).
        """
        rows = self._q("SELECT category, COUNT(*) as c FROM property GROUP BY category", many=True)
        return {r["category"]: r["c"] for r in rows}

    def update(self, prop_id: int, data: dict):
        """
        Mutates specific property parameters or flags state records during transaction completions.
        Ref: SDS §2.3 (Atomic state updates resetting availability flags to false on payment success).
        """
        is_avail = data.get("is_available", 1)
        self._exec(
            """UPDATE property SET
               title=?, description=?, price=?, location=?, category=?,
               bedrooms=?, bathrooms=?, area_sqm=?, has_garden=?, has_parking=?,
               office_spaces=?, lease_duration_months=?, security_deposit=?,
               is_available=?,
               sold_at = CASE WHEN ? = 1 THEN NULL ELSE sold_at END
               WHERE id=?""",
            (
                data["title"], data.get("description"), data["price"], data["location"], data["category"],
                data.get("bedrooms"), data.get("bathrooms"), data.get("area_sqm"), data.get("has_garden"), data.get("has_parking"),
                data.get("office_spaces"), data.get("lease_duration_months"), data.get("security_deposit"),
                is_avail, is_avail, prop_id
            )
        )

    def delete(self, prop_id: int):
        """
        Removes an individual structural listing row directly out of active data tables.
        """
        self._exec("DELETE FROM property WHERE id = ?", (prop_id,))