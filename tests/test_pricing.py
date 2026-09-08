import pytest
from decimal import Decimal, InvalidOperation

from foxprice.core.pricing import PricingEngine, PricingTier


@pytest.fixture
def engine() -> PricingEngine:
    return PricingEngine.from_rows(
        [
            ("0", "5", "300", 100),
            ("5", "10", "200", 50),
            ("10", "20", "150", 10),
            ("20", "999", "100", 1),
        ]
    )


@pytest.mark.parametrize(
    "price_str,expected_str",
    [
        ("0.01", "0.04"),  # 300% of 0.01 = 0.04
        ("4.99", "19.96"),  # 300% of 4.99 = 19.96
        ("5.00", "15.00"),  # 200% of 5.00 = 15.00, left boundary included
        ("9.99", "29.97"),  # 200% of 9.99 = 29.97
        ("10.00", "25.00"),  # 150% of 10.00 = 25.00
        ("19.99", "49.98"),  # 49.975 rounds to 49.98
        ("20.00", "40.00"),  # 100% of 20.00 = 40.00
    ],
)
def test_calculate_golden(engine, price_str, expected_str):
    assert str(engine.calculate(Decimal(price_str))[1]) == expected_str


def test_left_boundary_included(engine):
    tier = engine.find_tier(Decimal("5.00"))
    assert tier.price_from == Decimal("5")
    assert tier.price_to == Decimal("10")


def test_right_boundary_excluded(engine):
    tier = engine.find_tier(Decimal("10.00"))
    assert tier.price_from == Decimal("10")
    assert tier.price_to == Decimal("20")


def test_no_tier(engine):
    assert engine.calculate(Decimal("99999.00")) is None


def test_decimal_from_string_not_float():
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")


def test_from_rows_builds_correctly(engine):
    assert len(engine.tiers) == 4
    assert [t.price_from for t in engine.tiers] == sorted(
        t.price_from for t in engine.tiers
    )


def test_invalid_row_raises():
    with pytest.raises((InvalidOperation, ValueError)):
        PricingEngine.from_rows([("not_a_number", "5", "100", 1)])
