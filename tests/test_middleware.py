"""Tests for ScanUpload proxy middleware behavior."""

import httpx
import pytest

starlette = pytest.importorskip("starlette")

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from scan_upload_api_client import ScanUploadProxyOptions, TokenResponse
from scan_upload_api_client.middleware import ScanUploadProxyMiddleware
from tests.test_doubles import FakeTokenProvider


async def health(_: Request) -> JSONResponse:
    """Simple passthrough endpoint for middleware bypass checks."""
    return JSONResponse({"status": "ok"})


def _create_test_app(middleware_kwargs: dict) -> Starlette:
    app = Starlette(routes=[Route("/health", health)])
    app.add_middleware(ScanUploadProxyMiddleware, **middleware_kwargs)
    return app


@pytest.mark.asyncio
async def test_proxy_token_route_returns_token_payload() -> None:
    """Token route should return access token payload from token provider."""
    provider = FakeTokenProvider(TokenResponse(access_token="token-abc", expires_in=300))
    options = ScanUploadProxyOptions(
        route_prefix="/scanupload-api",
        token_route="/scanupload-api/token",
    )

    app = _create_test_app({"options": options, "token_provider": provider})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/scanupload-api/token")

    assert response.status_code == 200
    assert response.json()["access_token"] == "token-abc"
    assert response.json()["expires_in"] == 300
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_proxy_api_route_forwards_request_with_token_and_stripped_prefix() -> None:
    """API proxy route should forward with Bearer token and stripped route prefix."""
    provider = FakeTokenProvider(TokenResponse(access_token="token-xyz", expires_in=120))
    options = ScanUploadProxyOptions(
        target_base_url="https://upstream.local/api/front-end",
        route_prefix="/scanupload-api",
        token_route="/scanupload-api/token",
        strip_route_prefix=True,
    )

    captured: dict[str, str] = {}

    async def upstream_handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization", "")
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body"] = request.content.decode() if request.content else ""
        return httpx.Response(
            200,
            content=b'{"ok":true}',
            headers={"content-type": "application/json", "connection": "keep-alive"},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream_handler))
    app = _create_test_app(
        {
            "options": options,
            "token_provider": provider,
            "http_client": upstream_client,
        }
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/scanupload-api/session?x=1",
            json={"name": "alice"},
            headers={"x-request-id": "req-1"},
        )

    await upstream_client.aclose()

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "connection" not in response.headers

    assert captured["method"] == "POST"
    assert captured["url"] == "https://upstream.local/api/front-end/session?x=1"
    assert captured["authorization"] == "Bearer token-xyz"
    assert captured["content_type"].startswith("application/json")
    assert captured["body"] == '{"name":"alice"}'
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_non_proxy_route_passthrough() -> None:
    """Non-proxy routes should bypass middleware and reach app endpoints."""
    provider = FakeTokenProvider(TokenResponse(access_token="token-any", expires_in=60))
    options = ScanUploadProxyOptions(
        target_base_url="https://upstream.local",
        route_prefix="/scanupload-api",
        token_route="/scanupload-api/token",
    )

    app = _create_test_app({"options": options, "token_provider": provider})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert provider.calls == 0
