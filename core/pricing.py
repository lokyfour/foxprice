"""Pricing engine.

All arithmetic uses Decimal constructed from strings. float is never
used in this module. The single rounding rule is ROUND_HALF_UP to 2
decimal places. Tiers are loaded from the database (aiosqlite) at
runtime; this module only handles the calculation logic.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from loguru import logger


@dataclass
class PricingTier:
    price_from: Decimal
    price_to: Decimal  # exclusive upper bound
    markup_pct: Decimal
    min_order_qty: int = 1


class PricingEngine:
    def __init__(self, tiers: list[PricingTier]) -> None:
        self.tiers = sorted(tiers, key=lambda t: t.price_from)

    def find_tier(self, unit_price: Decimal) -> PricingTier | None:
        for tier in self.tiers:
            if tier.price_from <= unit_price < tier.price_to:
                return tier
        return None

    def calculate(self, unit_price: Decimal) -> tuple[Decimal, Decimal] | None:
        """Returns None if no tier matches — caller must handle."""
        tier = self.find_tier(unit_price)
        if tier is None:
            logger.warning(f"no tier for price {unit_price}")
            return None
        final = unit_price * (1 + tier.markup_pct / Decimal("100"))
        final = final.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (tier.markup_pct, final)

    @classmethod
    def from_rows(cls, rows: list[tuple]) -> "PricingEngine":
        tiers = []
        for row in rows:
            price_from_str, price_to_str, markup_pct_str, min_order_qty_int = row
            try:
                tiers.append(
                    PricingTier(
                        price_from=Decimal(price_from_str),
                        price_to=Decimal(price_to_str),
                        markup_pct=Decimal(markup_pct_str),
                        min_order_qty=min_order_qty_int,
                    )
                )
            except InvalidOperation as e:
                raise ValueError(f"Invalid price value in tier row: {row}") from e
        return cls(tiers)

    def __repr__(self) -> str:
        return f"PricingEngine(tiers={len(self.tiers)})"
