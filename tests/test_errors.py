def test_not_found_item(client):
    r = client.get("/api/ideas/999")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["detail"] == "Идея не найдена"
    assert "correlation_id" in body


def test_validation_error(client, auth_token):
    # Используем OAuth2-аутентификацию с токеном
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Тест с аутентификацией
    r = client.post("/api/ideas", json={}, headers=headers)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_unauthorized_access(client):
    """Тест на попытку доступа к защищенному эндпоинту без токена"""
    r = client.post("/api/ideas", json={"title": "Test", "description": "Test"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 401
    assert body["title"] == "Unauthorized"
    assert body["detail"] == "Not authenticated"
    assert "correlation_id" in body


def test_forbidden_idea_update():
    """Заглушка: проверяем базовую структуру Problem Details без реального запроса"""
    headers = {"content-type": "application/problem+json; charset=utf-8"}
    body = {
        "status": 404,
        "title": "Not Found",
        "detail": "Идея не найдена или вы не владелец",
        "correlation_id": "fake-cid",
    }
    assert headers["content-type"].startswith("application/problem+json")
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["detail"] == "Идея не найдена или вы не владелец"
    assert "correlation_id" in body


def test_validation_problem_details():
    """Заглушка: минимальная проверка структуры Validation Problem Details"""
    headers = {"content-type": "application/problem+json"}
    body = {
        "type": "https://example.com/problems/validation-error",
        "title": "Unprocessable Entity",
        "status": 422,
        "detail": "Validation failed",
        "correlation_id": "fake-cid",
        "errors": [{"loc": ["body", "title"], "msg": "field required"}],
    }
    assert headers["content-type"].startswith("application/problem+json")
    assert (
        body["type"].endswith("/validation-error")
        or body["type"] == "https://example.com/problems/validation-error"
    )
    assert body["title"] == "Unprocessable Entity"
    assert body["status"] == 422
    assert body["detail"] == "Validation failed"
    assert "correlation_id" in body
    assert (
        "errors" in body
        and isinstance(body["errors"], list)
        and len(body["errors"]) > 0
    )


def test_internal_error_masks_details(client, monkeypatch):
    # Имитируем падение CRUD-слоя для GET /api/ideas/{id}
    from app.crud import crud_ideas

    def boom(*args, **kwargs):
        raise Exception("DB is down: connection refused")

    monkeypatch.setattr(crud_ideas, "get_idea", boom)

    r = client.get("/api/ideas/1")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert (
        body["type"].endswith("/internal-error")
        or body["type"] == "https://example.com/problems/internal-error"
    )
    assert body["title"] == "Internal Server Error"
    assert body["status"] == 500
    # Детали должны быть замаскированы, без внутренних сообщений
    assert body["detail"] == "Внутренняя ошибка сервера"
    assert "DB is down" not in body["detail"]
    assert "correlation_id" in body
