def test_register_user(client):
    """Тест регистрации пользователя"""
    user_data = {
        "username": "newuser",
        "email": "new@example.com",
        "password": "securepass123",
    }

    response = client.post("/api/users/new", json=user_data)
    assert response.status_code == 201
    assert "user_id" in response.json()
    assert response.json()["username"] == user_data["username"]


def test_login_success(client, test_user):
    """Тест успешной аутентификации"""
    login_data = {"username": "testuser", "password": "password123"}

    response = client.post("/api/token", data=login_data)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    """Тест аутентификации с неверными учетными данными"""
    login_data = {"username": "wronguser", "password": "wrongpass"}

    response = client.post("/api/token", data=login_data)
    assert response.status_code == 401


def test_protected_endpoint_with_token(client, auth_token):
    """Тест доступа к защищенному эндпоинту с токеном"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = client.get("/api/users/me", headers=headers)

    assert response.status_code == 200
    assert "user_id" in response.json()
    assert "username" in response.json()


def test_protected_endpoint_without_token(client):
    """Тест доступа к защищенному эндпоинту без токена"""
    response = client.get("/api/users/me")
    assert response.status_code == 401
