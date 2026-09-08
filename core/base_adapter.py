"""Base adapter contract for Foxprice supplier adapters.

Uses the Template Method pattern: adapters override only the methods
they need (login, fetch_offers, and optionally logout /
is_session_expired), while the orchestrator drives the full lifecycle
(login -> fetch_offers loop -> logout) the same way for every supplier.
"""

from abc import ABC, abstractmethod

from playwright.async_api import BrowserContext

from core.models import ErrorResult, PriceOffer


class BaseAdapter(ABC):
    SUPPLIER_NAME: str = ""
    ADAPTER_TIMEOUT_SEC: int = 1800

    @abstractmethod
    async def login(self, context: BrowserContext) -> None:
        """Called once before fetch_offers. After login, call
        context.storage_state() for persistence."""
        ...

    @abstractmethod
    async def fetch_offers(
        self, context: BrowserContext, part_number: str
    ) -> tuple[list[PriceOffer], list[ErrorResult]]:
        """Search for one part number. Returns (offers, errors).
        Must NOT raise exceptions — write errors to the errors list instead.
        Retry and circuit breaker are handled by the orchestrator."""
        ...

    async def logout(self, context: BrowserContext) -> None:
        """Close server-side session. Default: no-op."""
        pass

    async def is_session_expired(self, context: BrowserContext) -> bool:
        """Override to detect session expiry. Default: False."""
        return False
