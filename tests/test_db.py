import pytest
import pytest_asyncio
import asyncio
import aiosqlite
from pathlib import Path
from unittest.mock import patch

from foxprice.web.db import (
    init_db,
    get_tiers,
    upsert_tier,
    delete_tier,
    get_runs,
    insert_run,
    update_run,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_path(tmp_path) -> Path:
    path = tmp_path / "test.db"
    with patch("foxprice.web.db.DB_PATH", path):
        await init_db()
        yield path


async def test_init_creates_tables(db_path):
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            rows = await cursor.fetchall()
    names = {row[0] for row in rows}
    assert {"users", "runs", "pricing_tiers", "parts"} <= names


async def test_init_creates_admin_user(db_path):
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT username FROM users WHERE username = ?", ("admin",)
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None


async def test_init_admin_password_is_hashed(db_path):
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("admin",)
        ) as cursor:
            row = await cursor.fetchone()
    assert row[0].startswith("$2b$")


async def test_init_idempotent(db_path):
    await init_db()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
    assert row[0] == 1


async def test_upsert_tier_insert(db_path):
    await upsert_tier("0", "5", "300", 100)
    tiers = await get_tiers()
    assert len(tiers) == 1
    assert tiers[0][1] == "0"


async def test_upsert_tier_update(db_path):
    await upsert_tier("0", "5", "300", 100)
    tiers = await get_tiers()
    tier_id = tiers[0][0]
    await upsert_tier("0", "5", "250", 50, tier_id=tier_id)
    tiers = await get_tiers()
    assert len(tiers) == 1
    assert tiers[0][3] == "250"


async def test_delete_tier(db_path):
    await upsert_tier("0", "5", "300", 100)
    tiers = await get_tiers()
    await delete_tier(tiers[0][0])
    assert await get_tiers() == []


async def test_get_tiers_ordered_by_price(db_path):
    await upsert_tier("10", "20", "100", 1)
    await upsert_tier("0", "10", "200", 1)
    tiers = await get_tiers()
    assert float(tiers[0][1]) < float(tiers[1][1])


async def test_insert_and_get_run(db_path):
    await insert_run("run001", 10, ["sup_a", "sup_b"])
    runs = await get_runs()
    assert len(runs) == 1
    assert runs[0][1] == "run001"
    assert runs[0][2] == "running"


async def test_update_run(db_path):
    await insert_run("run002", 5, ["sup_a"])
    await update_run("run002", "done", parts_found=4, errors=1, duration_sec=12.5)
    runs = await get_runs()
    assert runs[0][2] == "done"
    assert runs[0][4] == 4
    assert runs[0][6] == 12.5


async def test_get_runs_limit(db_path):
    for i in range(5):
        await insert_run(f"run{i:03d}", 1, ["sup_a"])
    assert len(await get_runs(limit=3)) == 3
