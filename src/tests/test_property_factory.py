# tests/test_property_factory.py
import pytest
from factories import (
    PropertyDTO,
    PropertyFactory,
    ResidentialProperty,
    CommercialProperty,
    RentalProperty,
)


class TestPropertyFactory:
    """Assert that each DTO type resolves to the correct concrete subclass."""

    def test_residential_dto_yields_residential_property(self):
        dto = PropertyDTO(
            title="Oak Villa", price=250_000, location="Athens",
            type="residential", bedrooms=3, bathrooms=2,
        )
        prop = PropertyFactory.create_property(dto)
        assert isinstance(prop, ResidentialProperty)

    def test_commercial_dto_yields_commercial_property(self):
        dto = PropertyDTO(
            title="City Office", price=800_000, location="Thessaloniki",
            type="commercial", office_spaces=10, has_parking=True,
        )
        prop = PropertyFactory.create_property(dto)
        assert isinstance(prop, CommercialProperty)

    def test_rental_dto_yields_rental_property(self):
        dto = PropertyDTO(
            title="Harbour Studio", price=950, location="Piraeus",
            type="rental", lease_duration_months=12, security_deposit=1_900,
        )
        prop = PropertyFactory.create_property(dto)
        assert isinstance(prop, RentalProperty)

    def test_factory_injects_matching_tax_strategy_per_type(self):
        cases = [("residential", 0.02), ("commercial", 0.05), ("rental", 0.01)]
        for prop_type, expected_rate in cases:
            dto = PropertyDTO(
                title="T", price=100_000, location="Athens",
                type=prop_type, lease_duration_months=1, security_deposit=0,
            )
            prop = PropertyFactory.create_property(dto)
            assert prop.tax_strategy.tax_rate() == expected_rate, prop_type

    def test_factory_auto_increments_ids(self):
        dto_a = PropertyDTO(title="A", price=100_000, location="Athens", type="residential")
        dto_b = PropertyDTO(title="B", price=200_000, location="Athens", type="commercial")
        p1 = PropertyFactory.create_property(dto_a)
        p2 = PropertyFactory.create_property(dto_b)
        assert p2.id == p1.id + 1

    def test_from_db_row_rehydrates_correct_subclass(self):
        row = {
            "title": "Loft", "price": 320_000, "location": "Kolonaki",
            "category": "residential", "bedrooms": 1, "bathrooms": 1,
        }
        prop = PropertyFactory.from_db_row(row)
        assert isinstance(prop, ResidentialProperty)

    def test_factory_rejects_invalid_type(self):
        dto = PropertyDTO(title="Bad", price=1_000, location="Athens", type="warehouse")
        with pytest.raises((ValueError, KeyError)):
            PropertyFactory.create_property(dto)

    def test_factory_rejects_empty_title(self):
        dto = PropertyDTO(title="", price=100_000, location="Athens", type="residential")
        with pytest.raises(ValueError, match="title"):
            PropertyFactory.create_property(dto)

    def test_factory_rejects_negative_price(self):
        dto = PropertyDTO(title="Villa", price=-1, location="Athens", type="residential")
        with pytest.raises(ValueError, match="price"):
            PropertyFactory.create_property(dto)