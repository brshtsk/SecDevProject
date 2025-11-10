import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def clear_buckets():
    # Сбрасываем состояние in-memory токенов перед и после каждого теста
    main.token_buckets._buckets.clear()
    yield
    main.token_buckets._buckets.clear()


@pytest.fixture
def advance_time(monkeypatch):
    # Контролируемое время для тестов с ожиданием окна
    t = {"now": 1_000_000.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(main.time, "time", fake_time)

    def _advance(seconds: float):
        t["now"] += seconds

    return _advance


def test_rate_limit_header_present(client, monkeypatch):
    # Настраиваем общий лимит POST: 2/мин, без burst
    monkeypatch.setattr(main, "RATE_LIMIT_POST_PER_MIN_PER_IP", 2)
    monkeypatch.setattr(main, "RATE_LIMIT_BURST", 0)

    # Любой POST путь — middleware добавит заголовки (даже если 404 дальше)
    r = client.post("/api/_rl_test", json={"x": 1})

    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Reset" in r.headers

    # Значения — целые числа
    int(r.headers["X-RateLimit-Limit"])
    int(r.headers["X-RateLimit-Remaining"])
    int(r.headers["X-RateLimit-Reset"])


def test_rate_limit_exceeded_returns_429_problem(client, monkeypatch):
    # Очень жесткий лимит: 1/мин, без burst
    monkeypatch.setattr(main, "RATE_LIMIT_POST_PER_MIN_PER_IP", 1)
    monkeypatch.setattr(main, "RATE_LIMIT_BURST", 0)

    # 1-й запрос — проходит
    client.post("/api/_rl_test", json={"x": 1})

    # 2-й — превышение
    r = client.post("/api/_rl_test", json={"x": 2})
    assert r.status_code == 429
    assert "application/problem+json" in r.headers.get("content-type", "")

    # Заголовки по ADR
    assert "Retry-After" in r.headers
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers
    assert "X-RateLimit-Reset" in r.headers

    # Значения корректно парсятся
    assert int(r.headers["X-RateLimit-Limit"]) == 1
    assert int(r.headers["X-RateLimit-Remaining"]) >= 0
    int(r.headers["X-RateLimit-Reset"])
    assert int(r.headers["Retry-After"]) >= 1

    body = r.json()
    assert body.get("status") == 429
    assert body.get("title") == "Too Many Requests"
    assert "too-many-requests" in (body.get("type") or "")
    assert "correlation_id" in body


def test_rate_limit_resets_after_window(client, monkeypatch, advance_time):
    # 2/мин, без burst => после 2-х запросов блок до пополнения ~30 сек для 1 токена
    monkeypatch.setattr(main, "RATE_LIMIT_POST_PER_MIN_PER_IP", 2)
    monkeypatch.setattr(main, "RATE_LIMIT_BURST", 0)

    r1 = client.post("/api/_rl_test", json={"i": 1})
    assert r1.status_code != 429

    r2 = client.post("/api/_rl_test", json={"i": 2})
    assert r2.status_code != 429

    r_blocked = client.post("/api/_rl_test", json={"i": 3})
    assert r_blocked.status_code == 429

    # Ждем, пока накапает хотя бы 1 токен (~30 сек)
    advance_time(31)

    r_after = client.post("/api/_rl_test", json={"i": 4})
    assert r_after.status_code != 429
    # И заголовки снова на месте
    assert "X-RateLimit-Limit" in r_after.headers
    assert "X-RateLimit-Remaining" in r_after.headers
    assert "X-RateLimit-Reset" in r_after.headers


def test_login_bruteforce_blocking(client, monkeypatch, advance_time):
    # Лимит логина по IP: 2 попытки/10 минут
    monkeypatch.setattr(main, "RATE_LIMIT_LOGIN_PER_10MIN_PER_IP", 2)

    # 2 успешных "попытки" (middleware пропускает дальше)
    r1 = client.post("/api/token", data={"username": "u", "password": "p"})
    assert r1.status_code != 429
    r2 = client.post("/api/token", data={"username": "u", "password": "p"})
    assert r2.status_code != 429

    # 3-я — блок
    r_block = client.post("/api/token", data={"username": "u", "password": "p"})
    assert r_block.status_code == 429
    assert "Retry-After" in r_block.headers
    assert "application/problem+json" in r_block.headers.get("content-type", "")

    # Через 100 сек — все еще блок (для 1 токена нужно ~300 сек)
    advance_time(100)
    r_still_blocked = client.post("/api/token", data={"username": "u", "password": "p"})
    assert r_still_blocked.status_code == 429

    # Через ~300+ сек — снова можно
    advance_time(210)  # суммарно 310 сек
    r_ok = client.post("/api/token", data={"username": "u", "password": "p"})
    assert r_ok.status_code != 429
    assert "X-RateLimit-Limit" in r_ok.headers
    assert "X-RateLimit-Remaining" in r_ok.headers
    assert "X-RateLimit-Reset" in r_ok.headers
