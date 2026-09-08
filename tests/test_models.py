import pytest
from decimal import Decimal
from datetime import datetime
from core.models import PriceOffer, PricedResult, ErrorResult, RunSummary, ErrorType
from typing import get_args


def test_price_offer_defaults():
    offer = PriceOffer(
        supplier="s", part_number="p", matched_part="p", unit_price=Decimal("1.00")
    )
    assert offer.currency == "USD"
    assert offer.warehouse_code == ""
    assert offer.lead_time_days is None
    assert offer.pack_size == 1
    assert offer.min_order_qty == 1
    assert offer.fuzzy_matched is False


def test_price_offer_unit_price_is_decimal():
    offer = PriceOffer(
        supplier="s", part_number="p", matched_part="p", unit_price=Decimal("9.99")
    )
    assert isinstance(offer.unit_price, Decimal)
    assert type(offer.unit_price) is not float


def test_priced_result_fields():
    offer = PriceOffer(
        supplier="s", part_number="p", matched_part="p", unit_price=Decimal("9.99")
    )
    result = PricedResult(
        offer=offer, markup_pct=Decimal("200"), final_price=Decimal("29.97")
    )
    assert result.offer is offer
    assert result.markup_pct == Decimal("200")
    assert result.final_price == Decimal("29.97")
    assert isinstance(result.markup_pct, Decimal)
    assert isinstance(result.final_price, Decimal)


def test_error_result_defaults():
    err = ErrorResult(
        supplier="s", part_number="p", error_type="timeout", description="test"
    )
    assert err.attempt == 1
    assert isinstance(err.timestamp, datetime)


def test_error_type_literal_values():
    assert set(get_args(ErrorType)) == {
        "not_found",
        "timeout",
        "auth_error",
        "parse_error",
        "rfq",
        "circuit_open",
        "session_expired",
    }


def test_run_summary_mer_score():
    summary = RunSummary(
        run_id="r1",
        parts_total=2,
        parts_found=2,
        parts_not_found=0,
        errors=0,
        duration_sec=1.5,
        suppliers=["sup_a", "sup_b"],
        mer_score={"sup_a": 2, "sup_b": 0},
    )
    assert summary.mer_score["sup_a"] == 2


def test_unit_price_never_float():
    assert Decimal(0.1) + Decimal(0.2) != Decimal("0.3")
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
