"""Test doubles and fixtures for testing."""

from collections.abc import Awaitable, Callable
import inspect
from typing import Any

import httpx

from scan_upload_api_client import TokenResponse


class FakeTokenProvider:
    """Fake token provider for testing."""

    def __init__(self, token_response: TokenResponse):
        self.token_response = token_response
        self.calls = 0

    async def get_access_token(self) -> TokenResponse:
        self.calls += 1
        return self.token_response


class FakeKeycloakClient:
    """Fake Keycloak client for testing."""

    def __init__(
        self,
        factory: Callable[[], Awaitable[TokenResponse] | TokenResponse],
    ):
        self.factory = factory
        self.calls = 0

    async def get_client_credentials_token(self) -> TokenResponse:
        self.calls += 1
        result = self.factory()
        if inspect.isawaitable(result):
            return await result
        return result


class FakeTransport(httpx.AsyncBaseTransport):
    """Fake HTTP transport for testing."""

    def __init__(
        self, handler: Callable[[httpx.Request], Awaitable[httpx.Response]]
    ):
        self.handler = handler
        self.last_request: httpx.Request | None = None
        self.captured_body: bytes | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        if request.content:
            self.captured_body = await request.aread()
        return await self.handler(request)


def create_response(
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
    text: str | None = None,
) -> httpx.Response:
    """Create a mock HTTP response."""
    content = text.encode() if text else b""
    if json_data:
        import json
        content = json.dumps(json_data).encode()
    
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"} if json_data else {},
    )
