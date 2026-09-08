import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from foxprice.core.base_adapter import BaseAdapter
from foxprice.core.session import SessionManager

pytestmark = pytest.mark.asyncio


def _mock_adapter():
    adapter = MagicMock(spec=BaseAdapter)
    adapter.SUPPLIER_NAME = "test_supplier"
    return adapter


@pytest.fixture
def session_dir(tmp_path) -> Path:
    path = tmp_path / ".sessions"
    with patch("foxprice.core.session.SESSION_DIR", path):
        yield path


async def test_save_writes_json(session_dir):
    mgr = SessionManager()
    adapter = _mock_adapter()
    ctx = MagicMock()
    ctx.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})

    await mgr.save(adapter, ctx)

    session_file = session_dir / "test_supplier.json"
    assert session_file.exists()
    assert json.loads(session_file.read_text()) == {"cookies": [], "origins": []}


async def test_restore_returns_true_when_file_exists(session_dir):
    mgr = SessionManager()
    adapter = _mock_adapter()
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "test_supplier.json").write_text(json.dumps({"cookies": []}))

    result = await mgr.restore(adapter)
    assert result is True


async def test_restore_returns_false_when_no_file(session_dir):
    mgr = SessionManager()
    adapter = _mock_adapter()

    result = await mgr.restore(adapter)
    assert result is False


async def test_invalidate_deletes_file(session_dir):
    mgr = SessionManager()
    adapter = _mock_adapter()
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "test_supplier.json"
    session_file.write_text(json.dumps({"cookies": []}))

    await mgr.invalidate(adapter)
    assert not session_file.exists()


async def test_invalidate_ok_when_no_file(session_dir):
    mgr = SessionManager()
    adapter = _mock_adapter()

    await mgr.invalidate(adapter)
