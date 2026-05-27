# tests/test_tax_strategies.py
import pytest
from strategies import (
    ResidentialTaxStrategy,
    CommercialTaxStrategy,
    RentalTaxStrategy,
    get_tax_strategy,
)
from factories import PropertyDTO, PropertyFactory


class TestTaxStrategies:
    """Verify calculate_tax() output for each concrete ITaxStrategy."""

    def test_residential_tax_is_2_percent(self):
        s = ResidentialTaxStrategy()
        assert s.calculate(100_000) == pytest.approx(2_000.0)
        assert s.tax_rate() == 0.02
        assert s.label() == "Residential Tax (2%)"

    def test_commercial_tax_is_5_percent(self):
        s = CommercialTaxStrategy()
        assert s.calculate(100_000) == pytest.approx(5_000.0)
        assert s.tax_rate() == 0.05
        assert s.label() == "Commercial Tax (5%)"

    def test_rental_tax_is_1_percent(self):
        s = RentalTaxStrategy()
        assert s.calculate(1_000) == pytest.approx(10.0)
        assert s.tax_rate() == 0.01
        assert s.label() == "Rental Tax (1%)"

    def test_price_with_tax_residential(self):
        assert ResidentialTaxStrategy().price_with_tax(100_000) == pytest.approx(102_000.0)

    def test_price_with_tax_commercial(self):
        assert CommercialTaxStrategy().price_with_tax(200_000) == pytest.approx(210_000.0)

    def test_calculate_tax_via_composed_property_object(self):
        """ITaxStrategy is composed into Property; verify delegation chain."""
        dto = PropertyDTO(
            title="Penthouse", price=400_000, location="Kolonaki", type="residential",
        )
        prop = PropertyFactory.create_property(dto)
        assert prop.calculate_tax() == pytest.approx(8_000.0)   # 2% of 400,000
        assert prop.total_price() == pytest.approx(408_000.0)

    def test_strategy_registry_returns_correct_types(self):
        assert isinstance(get_tax_strategy("residential"), ResidentialTaxStrategy)
        assert isinstance(get_tax_strategy("commercial"), CommercialTaxStrategy)
        assert isinstance(get_tax_strategy("rental"), RentalTaxStrategy)

    def test_unknown_category_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown property category"):
            get_tax_strategy("warehouse")

    def test_tax_rounding_to_two_decimal_places(self):
        """calculate() must return a value rounded to 2 dp."""
        s = ResidentialTaxStrategy()
        result = s.calculate(333_333)
        assert result == round(333_333 * 0.02, 2)