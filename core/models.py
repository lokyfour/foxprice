"""Core data containers for Foxprice.

All monetary fields use Decimal, never float, to avoid floating-point
rounding errors when computing and comparing prices. This module holds
pure data containers only; no business logic lives here.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

ErrorType = Literal[
    "not_found",
    "timeout",
    "auth_error",
    "parse_error",
    "rfq",
    "circuit_open",
    "session_expired",
]


@dataclass
class PriceOffer:
    supplier: str
    part_number: str
    matched_part: str
    unit_price: Decimal
    currency: str = "USD"
    warehouse_code: str = ""
    warehouse_label: str = ""
    lead_time_days: Optional[int] = None
    pack_size: int = 1
    min_order_qty: int = 1
    fuzzy_matched: bool = False
    request_price: bool = False
    rfq_only: bool = False


@dataclass
class PricedResult:
    offer: PriceOffer
    markup_pct: Decimal
    final_price: Decimal  # quantized to 0.01 using ROUND_HALF_UP


@dataclass
class ErrorResult:
    supplier: str
    part_number: str
    error_type: ErrorType
    description: str
    attempt: int = 1
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RunSummary:
    run_id: str
    parts_total: int
    parts_found: int
    parts_not_found: int
    errors: int
    duration_sec: float
    suppliers: list[str]
    mer_score: dict[str, int]
