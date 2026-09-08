"""Demo adapter for books.toscrape.com — a public static HTML demo site.

books.toscrape.com has no search and no concept of part numbers, so
this adapter does not implement real part_number matching. It simply
returns the first 3 books on the homepage as demo offers, all flagged
fuzzy_matched=True. Real adapters must implement actual matching
against part_number.
"""

from decimal import Decimal

from loguru import logger
from playwright.async_api import BrowserContext
from playwright.async_api import TimeoutError as PWTimeout

from foxprice.core.base_adapter import BaseAdapter
from foxprice.core.models import ErrorResult, PriceOffer

BASE_URL = "http://books.toscrape.com"
BOOK_CARDS = "article.product_pod"
BOOK_TITLE = "h3 > a"
BOOK_PRICE = "p.price_color"


class DemoStaticAdapter(BaseAdapter):
    SUPPLIER_NAME = "demo_static"
    ADAPTER_TIMEOUT_SEC = 120

    async def login(self, context: BrowserContext) -> None:
        logger.debug("demo_static: no login required")

    async def fetch_offers(
        self, context: BrowserContext, part_number: str
    ) -> tuple[list[PriceOffer], list[ErrorResult]]:
        page = await context.new_page()
        try:
            await page.goto(BASE_URL, timeout=15000)
            await page.wait_for_selector(BOOK_CARDS, timeout=10000)

            cards = await page.query_selector_all(BOOK_CARDS)
            offers: list[PriceOffer] = []

            for card in cards[:3]:
                title_el = await card.query_selector(BOOK_TITLE)
                price_el = await card.query_selector(BOOK_PRICE)
                if title_el is None or price_el is None:
                    continue

                title = (await title_el.inner_text()).strip()
                price_text = (await price_el.inner_text()).strip()
                cleaned = price_text.replace("Â£", "").replace("£", "").replace(",", "").strip()
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
                            description="no books found on demo_static homepage",
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
