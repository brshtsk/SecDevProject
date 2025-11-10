# ADR-001: Rate limiting и защита endpoint'ов

Дата: 21.10.2025
Статус: Accepted

## Context

Сервис подвержен риску DoS и целенаправленным атакам. Без
согласованной политики ограничения частоты запросов мы рискуем перегрузкой ресурсов.

Альтернативы:

- Ничего не делать - риски высоки
- Простая in-process rate limiting (memory-only) - недостаточно надежно для распределенного сервиса
- Распределенный rate-limiter на внешнем хранилище + middleware - компромисс между надежностью и сложностью,
  предпочтительный вариант

## Decision

1. Архитектура и реализация
    - Внедряем middleware/edge-policy, который применяет rate limits до попадания в основной обработчик
    - Политика реализации: основной алгоритм - **Token Bucket**
2. Категории лимитов и конфигурация (пороговые значения)
    - Глобальный limit для POST/PUT запросов по IP:
        - `RATE_LIMIT_POST_PER_MIN_PER_IP = 10`
        - `RATE_LIMIT_BURST = 2`
    - Специальный limit для аутентификации:
        - По IP: `RATE_LIMIT_LOGIN_PER_10MIN_PER_IP = 5`
        - По username/account: `RATE_LIMIT_LOGIN_PER_10MIN_PER_ACCOUNT = 5`
        - При достижении порога - временная блокировка аккаунта на 15 минут
3. Поведение при превышении
    - Возвращаем HTTP `429 Too Many Requests`
    - Тело ответа - по RFC 7807 (см. ADR-002) с `correlation_id` для логов
    - Заголовки ответа:
        - `Retry-After: <seconds>`
        - `X-RateLimit-Limit: <limit>`
        - `X-RateLimit-Remaining: <remaining>`
        - `X-RateLimit-Reset: <unix-timestamp>`
4. Логирование и метрики
    - Логируем каждое событие превышения как WARN с `correlation_id`
    - Настроить alerting: если `rate_limiter_blocked_total` растет > 1000/час - тревога
5. Тестирование и контракт
    - Добавить unit тесты с проверкой контракта ответа при превышении лимита
    - CI должно запускать нагрузочные unit-тесты

## Consequences

Плюсы:

- Эффективное уменьшение риска DoS и уменьшение влияния перебоев от шумных клиентов
- Прямая защита от brute-force
- Унифицированный механизм контроля и наблюдаемости

Минусы:

- Дополнительный зависимый компонент (Redis) - требует мониторинга и поддержки
- Возможность ложноположительных блокировок при NAT/прокси (несколько пользователей под одним IP)
- Борьба с распределенными атаками остается сложной задачей - rate-limiter дает только базовую защиту

## Links

- NFR-06 (Rate limiting)
- R1 (Bruteforce login)
- F3 (User → API (CRUD/голоса))
- tests/test_rate_limit.py::test_rate_limit_header_present
- tests/test_rate_limit.py::test_rate_limit_exceeded_returns_429_problem
- tests/test_rate_limit.py::test_rate_limit_resets_after_window
- tests/test_rate_limit.py::test_login_bruteforce_blocking
