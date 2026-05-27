"""
factories.py — HomeFinder Portal
PropertyDTO (Data Transfer Object) and PropertyFactory (Factory Method Pattern).

References:
- SDS Section 3.1: Factory Method - Property Factory[cite: 218].
- SRS FR-03 & FR-05: Property categorization (Residential, Commercial, Rental)[cite: 49, 222].

This module encapsulates conditional instantiation logic. By relying on PropertyFactory, 
adding a new property category requires zero modifications to PropertyService[cite: 220].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from strategies import ITaxStrategy, get_tax_strategy


# ---------------------------------------------------------------------------
# Data Transfer Object Boundary (SDS Section 2.2.2 / SDS Section 3)
# ---------------------------------------------------------------------------

@dataclass
class PropertyDTO:
    """
    Validated DTO passed to PropertyFactory. Ensures no unvalidated data 
    reaches the business logic layer[cite: 186].
    """

    title:    str
    price:    float
    location: str
    type:     str          # 'residential' | 'commercial' | 'rental'

    # Extended attributes supporting SRS FR-04 (Search filters) [cite: 49]
    description:           Optional[str]   = None
    bedrooms:              Optional[int]   = None
    bathrooms:             Optional[int]   = None
    area_sqm:              Optional[float] = None
    has_garden:            bool            = False
    has_parking:           bool            = False
    office_spaces:         Optional[int]   = None   # Maps to CommercialProperty [cite: 148]
    lease_duration_months: Optional[int]   = None
    security_deposit:      Optional[float] = None
    owner_id:              Optional[int]   = None

    # Legacy support
    category: Optional[str] = None

    VALID_TYPES = frozenset({"residential", "commercial", "rental"})

    def __post_init__(self):
        # Normalizes type/category inputs
        if self.category and not self.type:
            self.type = self.category
        if self.type:
            self.type = self.type.lower()
        if self.category:
            self.category = self.category.lower()

    def validate(self) -> bool:
        """
        Validates DTO fields before processing[cite: 167]. 
        Returns True if valid, raises ValueError otherwise.
        """
        if not self.title or not self.title.strip():
            raise ValueError("title must not be empty")
        if self.price < 0:
            raise ValueError("price must be non-negative")
        if not self.location or not self.location.strip():
            raise ValueError("location must not be empty")
        effective_type = self.type or self.category
        if not effective_type or effective_type not in self.VALID_TYPES:
            raise ValueError(f"type must be one of {self.VALID_TYPES}")
        return True

    @property
    def resolved_type(self) -> str:
        """Returns the active type/category classification."""
        return self.type or self.category or ""


# ---------------------------------------------------------------------------
# Abstract Domain Model (SDS Section 3.1 & 3.2)
# ---------------------------------------------------------------------------

class Property(ABC):
    """
    Abstract base class for properties. Holds a composition reference 
    to ITaxStrategy to delegate tax calculations dynamically[cite: 226].
    """

    def __init__(self, id: int, dto: PropertyDTO, tax_strategy: ITaxStrategy):
        self.id:           int          = id
        self.title:        str          = dto.title
        self.price:        float        = dto.price
        self.location:     str          = dto.location
        self.tax_strategy: ITaxStrategy = tax_strategy   # Strategy pattern injection [cite: 226]

        self.description:           Optional[str]   = dto.description
        self.bedrooms:              Optional[int]   = dto.bedrooms
        self.bathrooms:             Optional[int]   = dto.bathrooms
        self.area_sqm:              Optional[float] = dto.area_sqm
        self.has_garden:            bool            = dto.has_garden
        self.has_parking:           bool            = dto.has_parking
        self.office_spaces:         Optional[int]   = dto.office_spaces 
        self.lease_duration_months: Optional[int]   = dto.lease_duration_months
        self.security_deposit:      Optional[float] = dto.security_deposit
        self.owner_id:              Optional[int]   = dto.owner_id
        self.category:              str             = dto.resolved_type

    @abstractmethod
    def get_details(self) -> str:
        """Polymorphic method for generating human-readable property details."""

    def calculate_tax(self) -> float:
        """
        Delegates tax calculation to the injected ITaxStrategy at runtime, 
        eliminating conditionals from the domain model[cite: 226, 227].
        """
        return self.tax_strategy.calculate(self.price)

    # -- Convenience aliases ------------------------------------------------

    def tax_amount(self) -> float:
        return self.calculate_tax()

    def total_price(self) -> float:
        return self.tax_strategy.price_with_tax(self.price)

    def tax_label(self) -> str:
        return self.tax_strategy.label()

    def property_type(self) -> str:
        return self.category.capitalize()

    def to_dict(self) -> dict:
        """Serializes domain object to dict for repository persistence."""
        return {
            "title":                  self.title,
            "price":                  self.price,
            "location":               self.location,
            "category":               self.category,
            "description":            self.description,
            "bedrooms":               self.bedrooms,
            "bathrooms":              self.bathrooms,
            "area_sqm":               self.area_sqm,
            "has_garden":             1 if self.has_garden else 0,
            "has_parking":            1 if self.has_parking else 0,
            "office_spaces":          self.office_spaces,
            "lease_duration_months":  self.lease_duration_months,
            "security_deposit":       self.security_deposit,
            "owner_id":               self.owner_id,
            "property_type":          self.property_type(),
            "tax_amount":             self.tax_amount(),
            "total_price":            self.total_price(),
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} '{self.title}' €{self.price:,.2f}>"


# ---------------------------------------------------------------------------
# Concrete Products (SDS Section 3.1 & ERD Table 1)
# ---------------------------------------------------------------------------

class ResidentialProperty(Property):
    """Residential product implementation[cite: 219]."""

    def get_details(self) -> str:
        return (
            f"[Residential] {self.title} | €{self.price:,.2f} | "
            f"{self.location} | Bedrooms: {self.bedrooms} | "
            f"Garden: {'Yes' if self.has_garden else 'No'}"
        )


class CommercialProperty(Property):
    """Commercial product implementation. Includes office_spaces attribute[cite: 148, 219]."""

    def get_details(self) -> str:
        spaces_part = f" | Office spaces: {self.office_spaces}" if self.office_spaces else ""
        return (
            f"[Commercial] {self.title} | €{self.price:,.2f} | "
            f"{self.location}{spaces_part} | "
            f"Parking: {'Yes' if self.has_parking else 'No'}"
        )


class RentalProperty(Property):
    """Rental product implementation[cite: 219]."""

    def get_details(self) -> str:
        return (
            f"[Rental] {self.title} | €{self.price:,.2f}/mo | "
            f"{self.location} | Lease: {self.lease_duration_months} months | "
            f"Deposit: €{self.security_deposit:,.2f}"
        )


# ---------------------------------------------------------------------------
# Factory Method (SDS Section 3.1)
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type[Property]] = {
    "residential": ResidentialProperty,
    "commercial":  CommercialProperty,
    "rental":      RentalProperty,
}

_next_id: int = 1   # Replace with DB sequence in production


class PropertyFactory:
    """
    Factory that generates the correct Property subclass and injects 
    the corresponding ITaxStrategy based on the provided DTO[cite: 219].
    """

    @staticmethod
    def create_property(dto: PropertyDTO) -> Property:
        """
        Resolves concrete class, injects ITaxStrategy, and returns the product.
        Maintains high cohesion within the factory and low coupling in services[cite: 221].
        """
        global _next_id

        dto.validate()
        resolved = dto.resolved_type
        klass    = _TYPE_MAP[resolved]
        strategy = get_tax_strategy(resolved)   # ITaxStrategy resolved by type
        prop     = klass(_next_id, dto, strategy)
        _next_id += 1
        return prop

    @staticmethod
    def from_db_row(row: dict) -> Property:
        """Re-hydrates a Property domain object from a database row dict."""
        prop_type = row.get("category") or row.get("type") or "residential"

        dto = PropertyDTO(
            title                 = row["title"],
            price                 = row["price"],
            location              = row["location"],
            type                  = prop_type,
            description           = row.get("description"),
            bedrooms              = row.get("bedrooms"),
            bathrooms             = row.get("bathrooms"),
            area_sqm              = row.get("area_sqm"),
            has_garden            = bool(row.get("has_garden")),
            has_parking           = bool(row.get("has_parking")),
            office_spaces         = row.get("office_spaces"),
            lease_duration_months = row.get("lease_duration_months"),
            security_deposit      = row.get("security_deposit"),
            owner_id              = row.get("owner_id"),
        )
        return PropertyFactory.create_property(dto)