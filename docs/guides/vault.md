### 1) Запуск Vault (dev‑режим, небезопасно, только для локальной разработки)

```
docker run --name vault-dev --cap-add=IPC_LOCK -e VAULT_DEV_ROOT_TOKEN_ID=root -p 8200:8200 -d hashicorp/vault:1.15
```

Переменные окружения для CLI

```
$env:VAULT_ADDR = 'http://127.0.0.1:8200'
$env:VAULT_TOKEN = 'root'
```

### 2) Хранилище секретов и запись значений

```
vault secrets enable -path=secret-v2 kv-v2
```

Задайте свои значения...

```
vault kv put secret-v2/app SECRET_KEY="PLACEHOLDER_SUPER_SECRET_KEY"
vault kv put secret-v2/postgres POSTGRES_PASSWORD="PLACEHOLDER_STRONG_DB_PASSWORD"
```

### 3) Политика и AppRole для Vault Agent

Создадим файл политики (даёт read на нужные пути)

```
@"
path "secret-v2/data/app" {
capabilities = ["read"]
}
path "secret-v2/data/postgres" {
capabilities = ["read"]
}
"@ | Set-Content -Path policy.hcl -Encoding UTF8
```

```
python -c "b=open('policy.hcl','rb').read(); open('policy.hcl','wb').write(b[3:] if b.startswith(b'\xef\xbb\xbf') else
b)"
```

```
vault policy write app-read policy.hcl
vault auth enable approle
vault write auth/approle/role/app-role token_policies="app-read" token_ttl=1h token_max_ttl=4h
```

Получение идентификаторов

```
$ROLE_ID = (vault read -format=json auth/approle/role/app-role/role-id | ConvertFrom-Json).data.role_id
$SECRET_ID = (vault write -format=json -f auth/approle/role/app-role/secret-id | ConvertFrom-Json).data.secret_id
```

Сохранение в файлы, которые монтируются в контейнер агента (см. compose.base.yml)

```
New-Item -ItemType Directory -Force -Path vault, vault\templates, vault\rendered | Out-Null
$ROLE_ID | Set-Content -Path vault\role_id -Encoding UTF8 -NoNewline
$SECRET_ID | Set-Content -Path vault\secret_id -Encoding UTF8 -NoNewline
```

```
python -c "b=open(r'vault\secret_id','rb').read(); open(r'vault\secret_id','wb').write(b[3:] if b.startswith(
b'\xef\xbb\xbf') else b)"
python -c "b=open(r'vault\role_id','rb').read(); open(r'vault\role_id','wb').write(b[3:] if b.startswith(
b'\xef\xbb\xbf') else b)"
```
