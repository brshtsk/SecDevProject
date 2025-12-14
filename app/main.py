import logging
import math
import os
import time
from typing import Tuple
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import models
from app.database import SessionLocal, engine
from app.http_client import SafeHttpClient
from app.routers import ideas, users

app = FastAPI(title="Idea Voting Board", version="0.2.0")

# Лимиты запросов
RATE_LIMIT_POST_PER_MIN_PER_IP = int(os.getenv("RATE_LIMIT_POST_PER_MIN_PER_IP", "10"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "2"))
RATE_LIMIT_LOGIN_PER_10MIN_PER_IP = int(
    os.getenv("RATE_LIMIT_LOGIN_PER_10MIN_PER_IP", "5")
)

# Метрика блокировок
rate_limiter_blocked_total = 0

logger = logging.getLogger("rate_limiter")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

    path = request.url.path
    if path in ("/", "/health"):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, max-age=0, must-revalidate"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif path in ("/robots.txt", "/sitemap.xml"):
        response.headers["Cache-Control"] = "public, max-age=3600, immutable"
    return response


@app.get("/robots.txt")
def robots():
    content = "User-agent: *\nDisallow:"
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml")
def sitemap():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>http://localhost:8080/</loc></url>"
        "</urlset>"
    )
    return Response(content=xml, media_type="application/xml; charset=utf-8")


# Работаем с X-Correlation-ID
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(uuid4())
    request.state.correlation_id = cid
    try:
        response = await call_next(request)
    except Exception:
        raise
    response.headers["X-Correlation-ID"] = cid
    return response


def _type_for_status(status_code: int) -> str:
    mapping = {
        400: "https://example.com/problems/bad-request",
        401: "https://example.com/problems/unauthorized",
        403: "https://example.com/problems/forbidden",
        404: "https://example.com/problems/not-found",
        409: "https://example.com/problems/conflict",
        422: "https://example.com/problems/validation-error",
        429: "https://example.com/problems/too-many-requests",
        500: "https://example.com/problems/internal-error",
    }
    return mapping.get(status_code, "about:blank")


def _title_for_status(status_code: int) -> str:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }
    return titles.get(status_code, "Error")


# --- Простой in-memory Token Bucket ---
class _Bucket:
    __slots__ = ("tokens", "capacity", "refill_rate", "updated_at")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = float(capacity)
        self.updated_at = time.time()


class InMemoryTokenBuckets:
    def __init__(self):
        self._buckets: dict[str, _Bucket] = {}

    def _now(self) -> float:
        return time.time()

    def try_acquire(
        self, key: str, capacity: int, refill_per_sec: float, cost: float = 1.0
    ) -> Tuple[bool, int, int, int]:
        # Инициализация/обновление
        b = self._buckets.get(key)
        now = self._now()
        if (
            b is None
            or b.capacity != capacity
            or abs(b.refill_rate - refill_per_sec) > 1e-9
        ):
            b = _Bucket(capacity, refill_per_sec)
            self._buckets[key] = b
        # Рефил
        elapsed = max(0.0, now - b.updated_at)
        if elapsed > 0:
            b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_rate)
            b.updated_at = now
        # Попытка списать
        allowed = b.tokens >= cost
        if allowed:
            b.tokens -= cost
        remaining = max(0, int(math.floor(b.tokens)))
        # Когда восстановится до полной емкости
        missing = max(0.0, b.capacity - b.tokens)
        seconds_to_full = (
            int(math.ceil(missing / b.refill_rate)) if b.refill_rate > 0 else 0
        )
        reset_ts = int(now + seconds_to_full)
        return allowed, remaining, reset_ts, b.capacity


token_buckets = InMemoryTokenBuckets()


def _rate_limit_problem(
    request: Request,
    *,
    limit: int,
    remaining: int,
    reset_ts: int,
    retry_after_secs: int,
):
    headers = {
        "Retry-After": str(max(1, retry_after_secs)),
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(max(0, remaining)),
        "X-RateLimit-Reset": str(reset_ts),
    }
    # Логируем WARN
    cid = getattr(request.state, "correlation_id", "-")
    logger.warning("Rate limit exceeded: cid=%s path=%s", cid, request.url.path)
    global rate_limiter_blocked_total
    rate_limiter_blocked_total += 1
    return _problem_response(
        request,
        status_code=429,
        title=_title_for_status(429),
        detail="Rate limit exceeded",
        type_uri=_type_for_status(429),
        headers=headers,
    )


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method.upper()
    # Определяем IP клиента только по сокетному адресу (без X-Forwarded-For)
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Специальный лимит для логина по IP: 5/10мин
    if path.endswith("/token") and method == "POST":
        capacity = RATE_LIMIT_LOGIN_PER_10MIN_PER_IP  # без burst
        refill_per_sec = capacity / (10 * 60) if capacity > 0 else 0.0
        key = f"rl:login:ip:{client_ip}"
        allowed, remaining, reset_ts, limit = token_buckets.try_acquire(
            key, capacity, refill_per_sec, 1.0
        )
        if not allowed:
            retry_after = max(1, reset_ts - int(now))
            return _rate_limit_problem(
                request,
                limit=limit,
                remaining=remaining,
                reset_ts=reset_ts,
                retry_after_secs=retry_after,
            )
        # Пропускаем дальше, но добавим заголовки
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response

    # Общий лимит для POST/PUT по IP: 10/мин + burst 2 (capacity = 12, refill 10/мин)
    if method in ("POST", "PUT"):
        limit_per_min = RATE_LIMIT_POST_PER_MIN_PER_IP
        burst = RATE_LIMIT_BURST
        capacity = limit_per_min + burst
        refill_per_sec = limit_per_min / 60.0 if limit_per_min > 0 else 0.0
        key = f"rl:write:ip:{client_ip}"
        allowed, remaining, reset_ts, limit = token_buckets.try_acquire(
            key, capacity, refill_per_sec, 1.0
        )
        if not allowed:
            retry_after = max(1, reset_ts - int(now))
            return _rate_limit_problem(
                request,
                limit=limit,
                remaining=remaining,
                reset_ts=reset_ts,
                retry_after_secs=retry_after,
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response

    return await call_next(request)


def _problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    errors=None,
    type_uri: str | None = None,
    headers: dict | None = None,
):
    cid = getattr(request.state, "correlation_id", None) or str(uuid4())
    body = {
        "type": type_uri or _type_for_status(status_code),
        "title": title,
        "status": status_code,
        "detail": detail,
        "correlation_id": cid,
    }
    if errors is not None:
        body["errors"] = errors
    response = JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
        headers=headers or {},
    )
    response.headers["X-Correlation-ID"] = cid
    return response


# Старый класс можно оставить, но ответы тоже в формате Problem Details
class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return _problem_response(
        request,
        status_code=exc.status,
        title=_title_for_status(exc.status),
        detail=exc.message,
        errors={"code": exc.code},
        type_uri=_type_for_status(exc.status),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    status_code = exc.status_code
    title = _title_for_status(status_code)
    detail = exc.detail if isinstance(exc.detail, str) else title
    headers = getattr(exc, "headers", None) or {}
    return _problem_response(
        request,
        status_code=status_code,
        title=title,
        detail=detail,
        type_uri=_type_for_status(status_code),
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    status_code = exc.status_code
    title = _title_for_status(status_code)
    detail = exc.detail if isinstance(exc.detail, str) else title
    headers = getattr(exc, "headers", None) or {}
    return _problem_response(
        request,
        status_code=status_code,
        title=title,
        detail=detail,
        type_uri=_type_for_status(status_code),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _problem_response(
        request,
        status_code=422,
        title=_title_for_status(422),
        detail="Validation failed",
        errors=exc.errors(),
        type_uri=_type_for_status(422),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return _problem_response(
        request,
        status_code=500,
        title=_title_for_status(500),
        detail="Внутренняя ошибка сервера",
        type_uri=_type_for_status(500),
    )


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def wait_for_db():
    max_retries = 30
    retries = 0

    while retries < max_retries:
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            return True
        except OperationalError:
            retries += 1
            print(f"База данных недоступна, попытка {retries} из {max_retries}")
            time.sleep(2)

    return False


# Инициализация БД при старте
@app.on_event("startup")
async def startup():
    if wait_for_db():
        models.Base.metadata.create_all(bind=engine)
        print("База данных готова и таблицы созданы")
    else:
        print("Не удалось подключиться к базе данных")
    # Инициализация безопасного HTTP‑клиента
    app.state.http_client = SafeHttpClient()


@app.on_event("shutdown")
async def shutdown():
    client = getattr(app.state, "http_client", None)
    if client:
        await client.aclose()


# api пути
app.include_router(ideas.router, prefix="/api")
app.include_router(users.router, prefix="/api")
