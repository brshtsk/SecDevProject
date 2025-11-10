from unittest.mock import patch


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@patch("app.main.wait_for_db", return_value=False)
def test_startup_db_unavailable(mock_wait_for_db, client):
    """Тест поведения при недоступности БД при старте
    (требует моков для имитации ошибки БД)"""
    # Запускаем событие startup с мокнутой функцией wait_for_db
    # Это должно вызвать логирование ошибки о недоступности БД
    # Функция не выбрасывает исключение, но логирует ошибку
    import asyncio

    from app.main import startup

    asyncio.run(startup())

    # Проверяем что wait_for_db вызывалась
    mock_wait_for_db.assert_called_once()
