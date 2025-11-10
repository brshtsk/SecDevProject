def test_get_ideas_list(client):
    """Тест получения списка идей"""
    response = client.get("/api/ideas")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_idea_lifecycle(client, auth_token):
    """Тест полного жизненного цикла идеи - создание, чтение, обновление, удаление"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Создание идеи
    idea_data = {
        "title": "Тестовая идея",
        "description": "Описание тестовой идеи",
        "tags": ["тест", "api"],
    }

    create_response = client.post("/api/ideas", json=idea_data, headers=headers)
    assert create_response.status_code == 201
    created_idea = create_response.json()
    idea_id = created_idea["id"]

    # Получение идеи
    get_response = client.get(f"/api/ideas/{idea_id}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == idea_data["title"]

    # Обновление идеи
    update_data = {
        "title": "Обновленная идея",
        "description": "Обновленное описание",
        "tags": ["тест", "api", "обновлено"],
    }
    update_response = client.put(
        f"/api/ideas/{idea_id}", json=update_data, headers=headers
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == update_data["title"]

    # Удаление идеи
    delete_response = client.delete(f"/api/ideas/{idea_id}", headers=headers)
    assert delete_response.status_code == 204

    # Проверка, что идея удалена
    get_deleted = client.get(f"/api/ideas/{idea_id}")
    assert get_deleted.status_code == 404


def test_vote_for_idea(client, auth_token, db_session):
    """Тест голосования за идею"""
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Создание идеи
    idea_data = {
        "title": "Идея для голосования",
        "description": "Описание",
        "tags": ["голосование"],
    }
    idea = client.post("/api/ideas", json=idea_data, headers=headers).json()

    # Голосуем "за"
    vote_response = client.post(
        f"/api/ideas/{idea['id']}/vote", json={"value": "за"}, headers=headers
    )
    assert vote_response.status_code == 200
    assert "success" in vote_response.json()["status"]

    # Проверяем что идея имеет правильный счетчик голосов
    ideas_with_scores = client.get("/api/ideas").json()
    voted_idea = next(i for i in ideas_with_scores if i["id"] == idea["id"])
    assert voted_idea["up_votes"] == 1
    assert voted_idea["score"] == 1


def test_create_idea_validation_short_title(client, auth_token):
    """Создание идеи с коротким title должно вернуть 422"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    idea_data = {
        "title": "aa",  # _MIN_TITLE_LEN = 3
        "description": "Описание",
        "tags": [],
    }
    r = client.post("/api/ideas", json=idea_data, headers=headers)
    assert r.status_code == 422
    body = r.json()
    assert body.get("title") == "Unprocessable Entity"
    assert "Длина title" in body.get("detail", "")


def test_read_ideas_limit_query_validation(client):
    """Параметр limit > 100 должен вернуть 422 (валидация Query)"""
    r = client.get("/api/ideas?limit=1000")
    assert r.status_code == 422
    body = r.json()
    assert body.get("title") == "Unprocessable Entity"
    # В ответе должны быть детали валидации с указанием локации ошибки
    errors = body.get("errors", [])
    assert isinstance(errors, list) and errors
    assert any(
        isinstance(e.get("loc"), list)
        and len(e["loc"]) >= 2
        and e["loc"][0] == "query"
        and e["loc"][1] == "limit"
        for e in errors
    )
