"""
strategies.py — HomeFinder Portal
Tax-calculation Strategy Pattern.

References:
- SDS Section 3.2: Strategy - ITaxStrategy.
- SRS FR-03 & FR-04: Property categorization and filtering.

ITaxStrategy defines the interface. Each concrete strategy encapsulates the
tax-rate rule for a given property category, replacing conditional logic 
with polymorphic dispatch (Open/Closed Principle).
"""

from abc import ABC, abstractmethod


# ---------------------------------------------------------------------------
# Strategy Interface (SDS Section 3.2)
# ---------------------------------------------------------------------------

class ITaxStrategy(ABC):
    """
    Abstract strategy defining the contract for tax calculation.
    """

    @abstractmethod
    def calculate(self, amount: float) -> float:
        """Return the calculated tax amount for the given price."""

    @abstractmethod
    def tax_rate(self) -> float:
        """Return the decimal tax rate (e.g. 0.02 for 2%)."""

    def price_with_tax(self, price: float) -> float:
        """Convenience method returning the total price including tax."""
        return price + self.calculate(price)

    def label(self) -> str:
        """Return a human-readable tax label for UI presentation."""
        return f"{self.tax_rate() * 100:.1f}% tax"


# ---------------------------------------------------------------------------
# Concrete Strategies (SDS Section 3.2)
# ---------------------------------------------------------------------------

class ResidentialTaxStrategy(ITaxStrategy):
    """Applies a 2% residential property tax."""

    def calculate(self, amount: float) -> float:
        return round(amount * 0.02, 2)

    def tax_rate(self) -> float:
        return 0.02

    def label(self) -> str:
        return "Residential Tax (2%)"


class CommercialTaxStrategy(ITaxStrategy):
    """Applies a 5% commercial property tax."""

    def calculate(self, amount: float) -> float:
        return round(amount * 0.05, 2)

    def tax_rate(self) -> float:
        return 0.05

    def label(self) -> str:
        return "Commercial Tax (5%)"


class RentalTaxStrategy(ITaxStrategy):
    """Applies a 1% rental property tax."""

    def calculate(self, amount: float) -> float:
        return round(amount * 0.01, 2)

    def tax_rate(self) -> float:
        return 0.01

    def label(self) -> str:
        return "Rental Tax (1%)"


# ---------------------------------------------------------------------------
# Registry & Factory Helper (SDS Section 3.2)
# ---------------------------------------------------------------------------

TAX_STRATEGY_REGISTRY: dict[str, ITaxStrategy] = {
    "residential": ResidentialTaxStrategy(),
    "commercial":  CommercialTaxStrategy(),
    "rental":      RentalTaxStrategy(),
}


def get_tax_strategy(category: str) -> ITaxStrategy:
    """
    Return the appropriate ITaxStrategy instance for a given property category.
    Raises ValueError if the category is not registered.
    """
    strategy = TAX_STRATEGY_REGISTRY.get(category.lower())
    if strategy is None:
        raise ValueError(f"Unknown property category: {category!r}")
    return strategy