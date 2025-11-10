import logging
import math
import os
import re
import time
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import schemas
from app.auth import create_access_token, get_current_user
from app.crud import crud_users
from app.database import get_db

router = APIRouter(tags=["users"])

# Лимит запросов от пользователей
LOGIN_PER_10MIN_PER_ACCOUNT = int(
    os.getenv("RATE_LIMIT_LOGIN_PER_10MIN_PER_ACCOUNT", "5")
)
ACCOUNT_BLOCK_SECONDS = int(os.getenv("RATE_LIMIT_LOGIN_BLOCK_SECONDS", str(15 * 60)))

_logger = logging.getLogger("rate_limiter")


class _AcctBucket:
    __slots__ = ("tokens", "capacity", "refill_rate", "updated_at")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.updated_at = time.time()


_account_buckets: dict[str, _AcctBucket] = {}
_blocked_accounts: dict[str, float] = {}  # username -> unblock_at


def _acct_try_acquire(username: str) -> tuple[bool, int, int, int]:
    # Проверяет, можно ли сейчас совершить запрос и выдает инфу о текущем состоянии лимита
    now = time.time()
    # Проверка блокировки
    unblock_at = _blocked_accounts.get(username)
    if unblock_at is not None:
        if now < unblock_at:
            # Блок активен
            capacity = LOGIN_PER_10MIN_PER_ACCOUNT
            remaining = 0
            reset_ts = int(unblock_at)
            return False, remaining, reset_ts, capacity
        else:
            _blocked_accounts.pop(username, None)
    capacity = LOGIN_PER_10MIN_PER_ACCOUNT
    refill_per_sec = capacity / (10 * 60) if capacity > 0 else 0.0
    b = _account_buckets.get(username)
    if (
        b is None
        or b.capacity != capacity
        or abs(b.refill_rate - refill_per_sec) > 1e-9
    ):
        b = _AcctBucket(capacity, refill_per_sec)
        _account_buckets[username] = b
    elapsed = max(0.0, now - b.updated_at)
    if elapsed > 0:
        b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_rate)
        b.updated_at = now
    allowed = b.tokens >= 1.0
    if allowed:
        b.tokens -= 1.0
    remaining = max(0, int(math.floor(b.tokens)))
    missing = max(0.0, b.capacity - b.tokens)
    seconds_to_full = (
        int(math.ceil(missing / b.refill_rate)) if b.refill_rate > 0 else 0
    )
    reset_ts = int(now + seconds_to_full)
    return allowed, remaining, reset_ts, b.capacity


def _raise_429(username: str, remaining: int, reset_ts: int):
    retry_after = max(1, reset_ts - int(time.time()))
    headers = {
        "Retry-After": str(retry_after),
        "X-RateLimit-Limit": str(LOGIN_PER_10MIN_PER_ACCOUNT),
        "X-RateLimit-Remaining": str(max(0, remaining)),
        "X-RateLimit-Reset": str(reset_ts),
    }
    _logger.warning("Account rate limit exceeded: user=%s", username)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers=headers,
    )


def _enforce_account_login_limit(username: str):
    allowed, remaining, reset_ts, limit = _acct_try_acquire(username)
    if not allowed:
        # При достижении порога — блокировка аккаунта на 15 минут
        unblock_at = time.time() + ACCOUNT_BLOCK_SECONDS
        _blocked_accounts[username] = unblock_at
        # Во время блокировки клиенту возвращаем 429 с Retry-After до конца блокировки
        _raise_429(username, remaining=0, reset_ts=int(unblock_at))
    return limit, remaining, reset_ts


_MAX_USERNAME_LEN = 30
_MIN_USERNAME_LEN = 3
_USERNAME_RE = re.compile(r"^[a-z0-9_]+$")


def _normalize_username(v: str) -> str:
    v = v.strip().lower()
    v = re.sub(r"\s+", "_", v)  # пробелы -> _
    return v


def _validate_username(v: str):
    if len(v) < _MIN_USERNAME_LEN or len(v) > _MAX_USERNAME_LEN:
        raise HTTPException(
            status_code=422,
            detail=f"Длина username должна быть от {_MIN_USERNAME_LEN}"
            f"до {_MAX_USERNAME_LEN} символов",
        )
    if not _USERNAME_RE.fullmatch(v):
        raise HTTPException(
            status_code=422, detail="Username может содержать только [a-z0-9_]"
        )
    return v


@router.post(
    "/users/new", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED
)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Регистрация нового пользователя"""
    raw_username = _normalize_username(user.username)
    raw_username = _validate_username(raw_username)
    user.username = raw_username

    db_user = crud_users.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Пользователь с таким именем уже существует",
        )

    user = crud_users.create_user(db=db, user=user)

    # Возвращаем id
    return {
        "user_id": str(user.id),
        "username": user.username,
        "message": "Сохраните пароль! Его нельзя будет восстановить.",
    }


@router.post("/token")
def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    norm_username = _normalize_username(form_data.username)
    norm_username = _validate_username(norm_username)
    form_data.username = norm_username

    # Применяем per-account лимит ДО проверки пароля
    limit, remaining, reset_ts = _enforce_account_login_limit(form_data.username)
    # Заголовки лимита в успешном ответе
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_ts)

    user = crud_users.get_user_by_username(db, username=form_data.username)
    if not user or not crud_users.verify_password(
        form_data.password, user.hashed_password
    ):
        # В 401 тоже добавим заголовки лимита (и WWW-Authenticate)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={
                "WWW-Authenticate": "Bearer",
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_ts),
            },
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me")
def read_users_me(current_user=Depends(get_current_user)):
    return {"user_id": str(current_user.id), "username": current_user.username}
