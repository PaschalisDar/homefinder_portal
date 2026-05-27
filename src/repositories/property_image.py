"""
Module: repositories.property_image
Description: Controls file-system path linkages matching auxiliary binary listing resources.
References:
  - SRS FR-10: Administrators manage property listing attachments and user view components.
"""

from .base import BaseRepository

class PropertyImageRepository(BaseRepository):
    
    def add(self, property_id: int, image_path: str, display_order: int = 0):
        """
        Links an uploaded static path reference to a specific property card.
        """
        self._exec(
            "INSERT INTO property_image (property_id, image_path, display_order) VALUES (?, ?, ?)",
            (property_id, image_path, display_order),
        )

    def find_by_property(self, property_id: int) -> list[dict]:
        """
        Retrieves all categorized media assets assigned to a real estate listing card.
        """
        return self._q("SELECT * FROM property_image WHERE property_id = ? ORDER BY display_order ASC", (property_id,), many=True)

    def delete(self, image_id: int):
        """
        Removes an individual asset linkage record from relational context maps.
        """
        self._exec("DELETE FROM property_image WHERE id = ?", (image_id,))

    def delete_by_property(self, property_id: int):
        """
        Cascades detachment deletion sequences when a core structural listing is completely removed.
        """
        self._exec("DELETE FROM property_image WHERE property_id = ?", (property_id,))