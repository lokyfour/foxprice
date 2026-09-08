"""Session persistence for Foxprice supplier adapters.

SessionManager persists Playwright storageState (cookies + localStorage)
to disk so that authenticated sessions survive process restarts. The
.sessions/ directory must be listed in .gitignore because it contains
live authentication cookies.
"""

import json
from pathlib import Path

from loguru import logger
from playwright.async_api import BrowserContext

from foxprice.core.base_adapter import BaseAdapter

SESSION_DIR = Path(".sessions")


class SessionManager:
    """Persists and restores Playwright storage state per supplier.

    - save: writes the current context's storage_state() to
      .sessions/{supplier}.json.
    - restore: checks whether a session file exists for the adapter's
      supplier. It does NOT actually restore state onto an open
      context — Playwright only accepts storage_state at context
      creation time, so the real restore happens by passing the
      session file's path as the storage_state argument to
      browser.new_context(). This method only reports whether such a
      file is available for that call.
    - invalidate: deletes a supplier's saved session file, forcing a
      fresh login on the next run.

    The .sessions/ directory holds live authentication cookies and
    must never be committed to version control — it must be listed in
    .gitignore.
    """

    async def save(self, adapter: BaseAdapter, ctx: BrowserContext) -> None:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        state = await ctx.storage_state()
        path = SESSION_DIR / f"{adapter.SUPPLIER_NAME}.json"
        path.write_text(json.dumps(state))
        logger.info(f"{adapter.SUPPLIER_NAME}: session saved")

    async def restore(self, adapter: BaseAdapter) -> bool:
        path = SESSION_DIR / f"{adapter.SUPPLIER_NAME}.json"
        if path.exists():
            logger.info(
                f"{adapter.SUPPLIER_NAME}: session file found, will restore on next_context()"
            )
            return True
        return False

    async def invalidate(self, adapter: BaseAdapter) -> None:
        path = SESSION_DIR / f"{adapter.SUPPLIER_NAME}.json"
        if path.exists():
            path.unlink()
        logger.warning(f"{adapter.SUPPLIER_NAME}: session invalidated")
