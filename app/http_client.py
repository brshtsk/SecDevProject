import asyncio
import os
from typing import Any, Dict, Iterable, Optional

import httpx

# Базовые настройки из окружения
_TIMEOUT_TOTAL = float(os.getenv("HTTP_CLIENT_TIMEOUT_TOTAL", "10.0"))
_MAX_RETRIES = int(os.getenv("HTTP_CLIENT_MAX_RETRIES", "3"))
_BACKOFF_BASE = float(os.getenv("HTTP_CLIENT_BACKOFF_BASE", "0.25"))  # секунды
_CONCURRENCY_LIMIT = int(os.getenv("HTTP_CLIENT_CONCURRENCY", "10"))

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class SafeHttpClient:
    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._client = client or httpx.AsyncClient(follow_redirects=False)
        self._sem = asyncio.Semaphore(_CONCURRENCY_LIMIT)

    async def aclose(self):
        await self._client.aclose()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        data: Any = None,
        timeout: Optional[float] = None,
        allowed_retry_methods: Iterable[str] = (
            "GET",
            "HEAD",
            "OPTIONS",
            "DELETE",
            "PUT",
        ),
        correlation_id: Optional[str] = None,
    ) -> httpx.Response:
        timeout_val = timeout if timeout is not None else _TIMEOUT_TOTAL
        method_u = method.upper()
        retry_methods = {m.upper() for m in allowed_retry_methods}

        attempt = 0
        async with self._sem:
            while True:
                try:
                    req_headers = dict(headers or {})
                    if correlation_id and "X-Correlation-ID" not in req_headers:
                        req_headers["X-Correlation-ID"] = correlation_id

                    resp = await self._client.request(
                        method_u,
                        url,
                        headers=req_headers,
                        params=params,
                        json=json,
                        data=data,
                        timeout=timeout_val,  # общий таймаут
                    )

                    if (
                        method_u in retry_methods
                        and attempt < _MAX_RETRIES
                        and resp.status_code in _RETRY_STATUS_CODES
                    ):
                        attempt += 1
                        await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                        continue

                    return resp

                except (httpx.TimeoutException, httpx.TransportError):
                    if method_u in retry_methods and attempt < _MAX_RETRIES:
                        attempt += 1
                        await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                        continue
                    raise


# Зависимость для FastAPI
def get_http_client() -> SafeHttpClient:
    # Оставлено для совместимости: используйте Depends(injected_get_http_client)
    raise RuntimeError("Используйте Depends(injected_get_http_client)")


def injected_get_http_client(request) -> SafeHttpClient:
    return request.app.state.http_client
