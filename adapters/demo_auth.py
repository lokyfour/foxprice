"""Demo adapter for webscraper.io/test-sites/e-commerce/allinone — a
public site with no real authentication.

This adapter simulates the login -> session-check -> fetch lifecycle
that a real authenticated supplier adapter would follow, without an
actual credential flow. It exists so developers can exercise the full
orchestrator path (login, is_session_expired, fetch_offers, session
persistence) locally without needing a real supplier account.
"""

from decimal import Decimal

from loguru import logger
from playwright.async_api import BrowserContext
from playwright.async_api import TimeoutError as PWTimeout

from core.base_adapter import BaseAdapter
from core.models import ErrorResult, PriceOffer

# from settings import settings  # TODO

BASE_URL = "https://webscraper.io/test-sites/e-commerce/allinone"
PRODUCT_CARDS = "div.thumbnail"
PRODUCT_TITLE = "a.title"
PRODUCT_PRICE = "h4.price"
SESSION_CHECK = "div.thumbnail"  # presence = site loaded = "session ok"


class DemoAuthAdapter(BaseAdapter):
    SUPPLIER_NAME = "demo_auth"
    ADAPTER_TIMEOUT_SEC = 180

    async def login(self, context: BrowserContext) -> None:
        page = await context.new_page()
        try:
            await page.goto(BASE_URL, timeout=20000)
            await page.wait_for_selector(SESSION_CHECK, timeout=10000)
            logger.info("demo_auth: login OK (simulated — no real auth on this site)")
        finally:
            await page.close()

    async def is_session_expired(self, context: BrowserContext) -> bool:
        page = await context.new_page()
        try:
            await page.goto(BASE_URL, timeout=10000)
            try:
                await page.wait_for_selector(SESSION_CHECK, timeout=5000)
                return False
            except PWTimeout:
                return True
        finally:
            await page.close()

    async def fetch_offers(
        self, context: BrowserContext, part_number: str
    ) -> tuple[list[PriceOffer], list[ErrorResult]]:
        page = await context.new_page()
        try:
            await page.goto(BASE_URL, timeout=20000)
            await page.wait_for_selector(PRODUCT_CARDS, timeout=10000)

            cards = await page.query_selector_all(PRODUCT_CARDS)
            offers: list[PriceOffer] = []

            for card in cards[:3]:
                title_el = await card.query_selector(PRODUCT_TITLE)
                price_el = await card.query_selector(PRODUCT_PRICE)
                if title_el is None or price_el is None:
                    continue

                title = (await title_el.inner_text()).strip()
                price_text = (await price_el.inner_text()).strip()
                cleaned = price_text.replace("$", "").replace(",", "").strip()
                unit_price = Decimal(cleaned)

                offers.append(
                    PriceOffer(
                        supplier=self.SUPPLIER_NAME,
                        part_number=part_number,
                        matched_part=title,
                        unit_price=unit_price,
                        fuzzy_matched=True,
                    )
                )

            if not offers:
                return (
                    [],
                    [
                        ErrorResult(
                            supplier=self.SUPPLIER_NAME,
                            part_number=part_number,
                            error_type="not_found",
                            description="no products found on demo_auth homepage",
                        )
                    ],
                )

            return offers, []

        except PWTimeout as e:
            return (
                [],
                [
                    ErrorResult(
                        supplier=self.SUPPLIER_NAME,
                        part_number=part_number,
                        error_type="timeout",
                        description=str(e),
                    )
                ],
            )
        except Exception as e:
            return (
                [],
                [
                    ErrorResult(
                        supplier=self.SUPPLIER_NAME,
                        part_number=part_number,
                        error_type="parse_error",
                        description=str(e),
                    )
                ],
            )
        finally:
            await page.close()
