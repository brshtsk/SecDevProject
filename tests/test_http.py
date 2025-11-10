import asyncio

import httpx
import pytest

from app.http_client import SafeHttpClient


def test_retries_on_5xx_eventually_success(monkeypatch):
    monkeypatch.setattr("app.http_client._BACKOFF_BASE", 0.0, raising=True)
    monkeypatch.setattr("app.http_client._MAX_RETRIES", 2, raising=True)

    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(500, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    async def run():
        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)

        client = SafeHttpClient(client=async_client)
        try:
            resp = await client.request("GET", "https://example.test/resource")
            assert resp.status_code == 200
            assert calls["n"] == 3  # 2 неуспешных + 1 успешный
        finally:
            await client.aclose()

    asyncio.run(run())


def test_timeout_retries_then_raises(monkeypatch):
    monkeypatch.setattr("app.http_client._BACKOFF_BASE", 0.0, raising=True)
    monkeypatch.setattr("app.http_client._MAX_RETRIES", 1, raising=True)

    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        # Эмулируем таймаут на стороне транспорта
        raise httpx.ReadTimeout("simulated timeout", request=request)

    async def run():
        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)

        client = SafeHttpClient(client=async_client)
        try:
            with pytest.raises(httpx.ReadTimeout):
                await client.request("GET", "https://example.test/timeout")
            assert calls["n"] == 2  # 1 попытка + 1 ретрай
        finally:
            await client.aclose()

    asyncio.run(run())
