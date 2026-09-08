"""Foxprice web panel — FastAPI app.

Session auth uses short-lived JWT access tokens plus longer-lived
refresh tokens, both delivered as httponly cookies. User management
and system/admin routes (creating users, editing the admin password,
server health/config endpoints) are out of scope for this pass —
TODO: add a /users management UI and system routes once the admin
bootstrap flow (see web/db.py) has a proper rotation story.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite
import bcrypt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from loguru import logger

from foxprice.settings import settings
from foxprice.web.db import DB_PATH, delete_tier, get_runs, get_tiers, init_db, upsert_tier
from foxprice.web.runner import ALLOWED_SUPPLIERS, launch_run, stop_run
from foxprice.web.sse import get_bus

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
ALGORITHM = "HS256"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("web panel ready")
    yield
    logger.info("web panel shutting down")


app = FastAPI(title="Foxprice", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


# --- Auth helpers ---


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(seconds=settings.web_access_token_ttl),
        "type": "access",
    }
    return str(jwt.encode(payload, settings.web_secret_key, algorithm=ALGORITHM))


def create_refresh_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(seconds=settings.web_refresh_token_ttl),
        "type": "refresh",
    }
    return str(jwt.encode(payload, settings.web_secret_key, algorithm=ALGORITHM))


async def get_current_user(request: Request) -> str:
    # TODO: no /token/refresh route yet. The refresh_token cookie is
    # issued and stored but never consumed — once the 15-minute access
    # token expires, the user just hits a 401 and gets redirected to
    # /login instead of being silently re-authenticated via the
    # refresh token. Acceptable for v1, but implement rotation before
    # this ships somewhere that access tokens can't just be re-issued
    # by logging in again.
    token = request.cookies.get("access_token")
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")

    try:
        payload = jwt.decode(token, settings.web_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token"
        )

    return str(payload["sub"])


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# --- Auth routes ---


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request, "login.html")


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    assert isinstance(username, str)
    assert isinstance(password, str)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None or not bcrypt.checkpw(password.encode(), row[0].encode()):
        return TEMPLATES.TemplateResponse(request, "login.html", {"error": "Invalid credentials"})

    access_token = create_access_token(username)
    refresh_token = create_refresh_token(username)

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.web_access_token_ttl,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.web_refresh_token_ttl,
    )
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


# --- Dashboard routes ---


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: str = Depends(get_current_user)):
    runs = await get_runs()
    return TEMPLATES.TemplateResponse(request, "dashboard.html", {"runs": runs})


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str, user: str = Depends(get_current_user)):
    return TEMPLATES.TemplateResponse(request, "run_detail.html", {"run_id": run_id})


@app.get("/runs/{run_id}/stream")
async def run_stream(run_id: str, user: str = Depends(get_current_user)):
    bus = get_bus(run_id)
    if bus is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")

    queue = await bus.subscribe()

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/runs/start")
async def start_run(request: Request, user: str = Depends(get_current_user)):
    body = await request.json()
    skip = body.get("skip", [])
    parallel = body.get("parallel", False)
    parts_file = body.get("parts_file") or settings.parts_file

    try:
        with open(parts_file) as f:
            parts_total = sum(1 for line in f if line.strip())
    except OSError:
        parts_total = 0

    run_id = str(uuid.uuid4())[:8]
    asyncio.create_task(
        launch_run(
            run_id,
            parts_total=parts_total,
            suppliers=list(ALLOWED_SUPPLIERS),
            skip=skip,
            parallel=parallel,
        )
    )
    return JSONResponse({"run_id": run_id, "status": "started"})


@app.post("/runs/{run_id}/stop")
async def stop_run_route(run_id: str, user: str = Depends(get_current_user)):
    await stop_run(run_id)
    return JSONResponse({"status": "stopped"})


# --- Pricing tiers routes ---


@app.get("/tiers", response_class=HTMLResponse)
async def tiers_page(request: Request, user: str = Depends(get_current_user)):
    tiers = await get_tiers()
    return TEMPLATES.TemplateResponse(request, "tiers.html", {"tiers": tiers})


@app.post("/tiers")
async def tiers_upsert(request: Request, user: str = Depends(get_current_user)):
    form = await request.form()
    price_from = form.get("price_from")
    price_to = form.get("price_to")
    markup_pct = form.get("markup_pct")
    min_order_qty = form.get("min_order_qty", "1")
    tier_id = form.get("tier_id")
    assert isinstance(price_from, str)
    assert isinstance(price_to, str)
    assert isinstance(markup_pct, str)
    assert isinstance(min_order_qty, str)
    assert isinstance(tier_id, str)
    await upsert_tier(
        price_from=price_from,
        price_to=price_to,
        markup_pct=markup_pct,
        min_order_qty=int(min_order_qty),
        tier_id=int(tier_id) if tier_id else None,
    )
    return RedirectResponse(url="/tiers", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/tiers/{tier_id}/delete")
async def tiers_delete(tier_id: int, user: str = Depends(get_current_user)):
    await delete_tier(tier_id)
    return RedirectResponse(url="/tiers", status_code=status.HTTP_303_SEE_OTHER)


# TODO: user management routes (create/list/delete users, rotate admin
# password) and system routes (health check, config view) are not
# implemented yet.
