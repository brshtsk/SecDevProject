[![CI](https://github.com/brshtsk/SecDevProject/actions/workflows/ci.yml/badge.svg?branch=P08-cicd-minimal)](https://github.com/brshtsk/SecDevProject/actions/workflows/ci.yml)

# Idea Voting Board

Доска голосований за идеи команды

### Запуск в режиме разработки

В режиме разработки используется SQLite. Алгоритм запуска:

1) Запустить Vault локально (инструкция в [docs/guides/vault.md](docs/guides/vault.md))
2) Запустить Vault Agent для получения секретов из Vault:
```bash
docker compose -f compose.base.yml up -d vault-agent
```
3) Запустить сервисы в dev режиме:
```bash
docker compose -f compose.base.yml -f compose.dev.yml --profile dev up -d --build
```

### Запуск в продакшн режиме

В режиме продакшн compose поднимает Postgres. Алгоритм запуска:
1) Запустить Vault локально (инструкция в [docs/guides/vault.md](docs/guides/vault.md))
2) Запустить Vault Agent для получения секретов из Vault:
```bash
docker compose -f compose.base.yml up -d vault-agent
```
3) Запустить сервисы в prod режиме:
```bash
docker compose -f compose.base.yml -f compose.prod.yml --profile prod up -d --build
```

### API

#### Аутентификация и пользователи

- `POST /api/users/new` - Регистрация нового пользователя

- `POST /api/token` - Получение токена доступа (требуется логин и пароль)

- `GET /api/users/me` - Информация о текущем пользователе (требуется токен пользователя)

#### Идеи и голосования

- `GET /api/ideas` - Получение списка созданных идей с рейтингами

- `GET /api/ideas/{idea_id}` - Получение конкретной идеи по ID

- `POST /api/ideas` - Создание новой идеи (требуется токен владельца)

- `PUT /api/ideas/{idea_id}` - Обновление существующей идеи (требуется токен владельца)

- `DELETE /api/ideas/{idea_id}` - Удаление идеи (требуется токен владельца)

- `POST /api/ideas/{idea_id}/vote` - Голосование за идею (требуется токен пользователя)

### Аутентификация и безопасность

Используется JWT (живет 60 минут) для аутентификации пользователей:

1. **Регистрация**: `POST /api/users/new`
2. **Получение токена**: `POST /api/token` (требуется логин и пароль)
3. **Использование токена**: Включите токен в заголовок `Authorization: Bearer {token}` для защищенных
   запросов

## Работа с репозиторием

### Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
uvicorn app.main:app --reload
```

### Ритуал перед PR

```bash
ruff --fix .
black .
isort .
pytest -q
pre-commit run --all-files
```

### Тесты

```bash
pytest -q
```

### CI

В репозитории настроен workflow **CI** (GitHub Actions) — required check для `main`.
Badge добавится автоматически после загрузки шаблона в GitHub.

### Контейнеры

```bash
docker build -t secdev-app .
docker run --rm -p 8000:8000 secdev-app
# или
docker compose up --build
```

### Эндпойнты

- `GET /health` → `{"status": "ok"}`
- `POST /items?name=...` — демо-сущность
- `GET /items/{id}`

## Security: SBOM & SCA

- Инструменты:
  - SBOM: Syft (CycloneDX JSON)
  - SCA: Grype по SBOM
- Запуск: GitHub Actions workflow “Security SBOM & SCA”
  - Триггеры: workflow_dispatch, push/pull_request по *.py, requirements*.txt и самому workflow
- Артефакты (доказательство того, что CI действительно сделал SBOM и SCA для конкретного коммита):
  - EVIDENCE/P09/sbom.json
  - EVIDENCE/P09/sca_report.json
  - EVIDENCE/P09/sca_summary.md

## Security: SAST & Secrets

- Инструменты:
  - SAST: Semgrep (профиль p/ci + правила из security/semgrep/rules.yml)
  - Secrets: Gitleaks (конфиг security/.gitleaks.toml)
- Запуск: GitHub Actions workflow “Security SAST & Secrets”
  - Триггеры: workflow_dispatch, push по *.py, security-конфигах и самому workflow
- Артефакты:
  - EVIDENCE/P10/semgrep.sarif
  - EVIDENCE/P10/gitleaks.json
  - EVIDENCE/P10/sast_summary.md
- Политика:
  - Findings не ломают сборку (|| true), триаж в PR-описании
  - Ложные срабатывания добавляются в allowlist .gitleaks.toml с комментарием
