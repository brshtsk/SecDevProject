Добро пожаловать в документацию SecDevProject.

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
