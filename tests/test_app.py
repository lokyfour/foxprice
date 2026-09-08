import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from jose import jwt

from web.app import app
from settings import settings

ALGORITHM = "HS256"


def make_token(username: str = "admin") -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(seconds=900),
        "type": "access",
    }
    return jwt.encode(payload, settings.web_secret_key, algorithm=ALGORITHM)


def auth_cookies(client, username: str = "admin") -> dict:
    return {"access_token": make_token(username)}


def _mock_db_row(row):
    """Builds a mock aiosqlite connect()/execute() chain that returns
    `row` from cursor.fetchone(), for patching web.app.aiosqlite.connect."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=row)

    mock_cursor_cm = AsyncMock()
    mock_cursor_cm.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor_cm.__aexit__ = AsyncMock(return_value=False)

    mock_db = MagicMock()
    mock_db.execute = MagicMock(return_value=mock_cursor_cm)

    mock_connect_cm = AsyncMock()
    mock_connect_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_connect_cm.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=mock_connect_cm)


@pytest.fixture
def client():
    with patch("web.app.init_db", AsyncMock()):
        with TestClient(app) as c:
            yield c


def test_login_page_returns_200(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Sign in" in resp.text


def test_login_post_invalid_credentials(client):
    with patch("web.app.aiosqlite.connect", _mock_db_row(None)):
        resp = client.post(
            "/login",
            data={"username": "bad", "password": "bad"},
            follow_redirects=False,
        )
    assert resp.status_code == 200
    assert "Invalid credentials" in resp.text


def test_dashboard_requires_auth(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/login" in resp.headers["location"]


def test_dashboard_with_auth(client):
    with patch("web.app.get_runs", AsyncMock(return_value=[])):
        resp = client.get("/", cookies=auth_cookies(client))
    assert resp.status_code == 200


def test_tiers_requires_auth(client):
    resp = client.get("/tiers", follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_tiers_with_auth(client):
    with patch("web.app.get_tiers", AsyncMock(return_value=[])):
        resp = client.get("/tiers", cookies=auth_cookies(client))
    assert resp.status_code == 200


def test_run_detail_with_auth(client):
    resp = client.get("/runs/test123", cookies=auth_cookies(client))
    assert resp.status_code == 200
    assert "test123" in resp.text


def test_logout_clears_cookies(client):
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "access_token" not in resp.cookies or resp.cookies.get("access_token") == ""


def test_start_run_with_auth(client):
    with (
        patch("web.app.launch_run", AsyncMock()),
        patch("web.app.asyncio.create_task", side_effect=lambda coro: coro.close()),
    ):
        resp = client.post(
            "/runs/start",
            json={"skip": [], "parallel": False},
            cookies=auth_cookies(client),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "started"


def test_stream_run_not_found(client):
    resp = client.get("/runs/nonexistent/stream", cookies=auth_cookies(client))
    assert resp.status_code == 404


def test_expired_token_redirects_to_login(client):
    expired_payload = {
        "sub": "admin",
        "exp": datetime.utcnow() - timedelta(seconds=1),
        "type": "access",
    }
    expired_token = jwt.encode(expired_payload, settings.web_secret_key, algorithm=ALGORITHM)
    resp = client.get("/", cookies={"access_token": expired_token}, follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/login" in resp.headers["location"]
