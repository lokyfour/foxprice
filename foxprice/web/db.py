"""SQLite persistence for the Foxprice web panel.

Uses aiosqlite with WAL mode so the web panel and orchestrator can
read/write concurrently without locking the whole database.
"""

from pathlib import Path
from typing import Any

import aiosqlite
import bcrypt
from loguru import logger

DB_PATH = Path("web/foxprice.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                parts_total INTEGER,
                parts_found INTEGER,
                errors INTEGER,
                duration_sec REAL,
                suppliers TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_tiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                price_from TEXT NOT NULL,
                price_to TEXT NOT NULL,
                markup_pct TEXT NOT NULL,
                min_order_qty INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_number TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                target_price TEXT,
                run_id TEXT
            )
            """
        )

        await db.commit()

        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            assert row is not None
            user_count = row[0]

        if user_count == 0:
            password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt(rounds=13)).decode()
            await db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", password_hash),
            )
            await db.commit()
            logger.warning("default admin user created — change password immediately")

    logger.info(f"database initialised: {DB_PATH}")


async def get_tiers() -> list[Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM pricing_tiers ORDER BY CAST(price_from AS REAL)"
        ) as cursor:
            rows = await cursor.fetchall()
            return list(rows)


async def upsert_tier(
    price_from: str,
    price_to: str,
    markup_pct: str,
    min_order_qty: int,
    tier_id: int | None = None,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if tier_id is not None:
            await db.execute(
                """
                UPDATE pricing_tiers
                SET price_from = ?, price_to = ?, markup_pct = ?, min_order_qty = ?
                WHERE id = ?
                """,
                (price_from, price_to, markup_pct, min_order_qty, tier_id),
            )
        else:
            await db.execute(
                """
                INSERT INTO pricing_tiers (price_from, price_to, markup_pct, min_order_qty)
                VALUES (?, ?, ?, ?)
                """,
                (price_from, price_to, markup_pct, min_order_qty),
            )
        await db.commit()


async def delete_tier(tier_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pricing_tiers WHERE id = ?", (tier_id,))
        await db.commit()


async def get_runs(limit: int = 50) -> list[Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return list(rows)


async def insert_run(run_id: str, parts_total: int, suppliers: list[str]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO runs (run_id, parts_total, suppliers, status)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, parts_total, ",".join(suppliers), "running"),
        )
        await db.commit()


async def update_run(
    run_id: str, status: str, parts_found: int, errors: int, duration_sec: float
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE runs
            SET status = ?, parts_found = ?, errors = ?, duration_sec = ?
            WHERE run_id = ?
            """,
            (status, parts_found, errors, duration_sec, run_id),
        )
        await db.commit()
