# tests/conftest.py
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]  # корень репозитория
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.crud.crud_users import create_user  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import UserCreate  # noqa: E402

# SQLite в памяти для тестов
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True, scope="function")
def reset_rate_limiter():
    """
    Сбрасывает состояние in-memory rate limiter'а перед каждым тестом,
    чтобы тесты не влияли друг на друга.
    """
    from app import main as app_main
    from app.routers import users as users_router

    # IP-based (POST/PUT, /token) лимит
    app_main.token_buckets = app_main.InMemoryTokenBuckets()
    # Account-based login лимит
    users_router._account_buckets.clear()
    users_router._blocked_accounts.clear()
    yield


@pytest.fixture(scope="function")
def db_session():
    """Создает чистую БД для каждого теста и удаляет её после"""
    Base.metadata.create_all(bind=engine)

    # Создаем тестовую сессию
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Удаляем все данные после теста
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Создает тестовый клиент с перенаправлением на тестовую БД"""

    # Переопределяем зависимость для использования тестовой БД
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    class RetryClient:
        def __init__(
            self, inner, max_retries=2, default_backoff=0.05, max_total_wait=0.3
        ):
            self._c = inner
            self._max = max_retries
            self._backoff = default_backoff
            self._max_total = max_total_wait

        @property
        def app(self):
            return self._c.app

        def request(self, method, url, retry_on_429=False, **kwargs):
            headers = kwargs.pop("headers", None) or {}
            # Можно оставить X-Forwarded-For, лимитер его не использует
            headers.setdefault("X-Forwarded-For", f"test-{uuid4()}")
            deadline = time.monotonic() + self._max_total
            last_resp = None
            for attempt in range(self._max + 1):
                resp = self._c.request(method, url, headers=headers, **kwargs)
                last_resp = resp
                if not retry_on_429 or resp.status_code != 429 or attempt == self._max:
                    return resp
                # Ограничиваем задержку: игнорируем большие Retry-After и ставим короткий кап
                delay = min(self._backoff * (attempt + 1), 0.1)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return resp
                time.sleep(min(delay, max(0, remaining)))
            return last_resp

        # Удобные шорткаты
        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url, **kwargs):
            return self.request("PUT", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

        def patch(self, url, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def options(self, url, **kwargs):
            return self.request("OPTIONS", url, **kwargs)

        def head(self, url, **kwargs):
            return self.request("HEAD", url, **kwargs)

    # Важно: не пробрасываем исключения сервера наружу, чтобы получить корректный 500-ответ
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield RetryClient(test_client)

    # Очистка переопределений после теста
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(client, db_session):
    """Создает тестового пользователя для авторизации"""
    user_data = UserCreate(
        username="testuser", email="test@example.com", password="password123"
    )
    user = create_user(db_session, user_data)

    return {"user_id": user.id, "password": "password123"}


@pytest.fixture(scope="function")
def auth_token(client, test_user):
    response = client.post(
        "/api/token", data={"username": "testuser", "password": "password123"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]
