"""ASGI middleware for ScanUpload token and API proxy routes."""

from __future__ import annotations

import asyncio
from typing import Protocol

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from .exceptions import ScanUploadProxyException
from .options import ScanUploadProxyOptions


class TokenProviderProtocol(Protocol):
    """Protocol for token provider used by proxy middleware."""

    async def get_access_token(self) -> object: ...


class ScanUploadProxyMiddleware(BaseHTTPMiddleware):
    """Proxy middleware compatible with FastAPI/Starlette apps."""

    _RESTRICTED_HEADERS = {
        "host",
        "connection",
        "upgrade",
        "keep-alive",
        "proxy-connection",
        "transfer-encoding",
        "content-length",
        "content-encoding",
    }

    def __init__(
        self,
        app,
        options: ScanUploadProxyOptions,
        token_provider: TokenProviderProtocol | None = None,
        token_provider_state_key: str = "scan_upload_token_provider",
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(app)
        self._options = options
        self._token_provider = token_provider
        self._token_provider_state_key = token_provider_state_key
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=self._options.request_timeout.total_seconds(),
            follow_redirects=True,
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if self._is_token_route(path):
            return await self._proxy_token_route(request)

        if self._is_api_proxy_route(path):
            return await self._proxy_api_request(request)

        return await call_next(request)

    async def close(self) -> None:
        """Close owned HTTP client resources."""
        if self._owns_client:
            await self._http_client.aclose()

    def _is_token_route(self, path: str) -> bool:
        token_route = self._normalize_path(self._options.token_route)
        if not token_route:
            return False
        return path.casefold() == token_route.casefold()

    def _is_api_proxy_route(self, path: str) -> bool:
        route_prefix = self._normalize_path(self._options.route_prefix)
        if not route_prefix:
            return False
        path_cf = path.casefold()
        prefix_cf = route_prefix.casefold()
        return path_cf == prefix_cf or path_cf.startswith(f"{prefix_cf}/")

    async def _proxy_token_route(self, request: Request) -> Response:
        token_provider = self._resolve_token_provider(request)
        token = await token_provider.get_access_token()

        return JSONResponse(
            {
                "access_token": getattr(token, "access_token", ""),
                "expires_in": getattr(token, "expires_in", 0),
                "token_type": getattr(token, "token_type", "bearer"),
            }
        )

    async def _proxy_api_request(self, request: Request) -> Response:
        try:
            token_provider = self._resolve_token_provider(request)
            token = await token_provider.get_access_token()

            target_url = self._build_target_url(request)
            headers = self._build_proxy_headers(request)
            access_token = getattr(token, "access_token", "")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

            try:
                body = await request.body()
            except ClientDisconnect:
                return Response(status_code=499)
            method_upper = request.method.upper()
            content: bytes | None = None
            if body and method_upper not in {"GET", "HEAD", "DELETE"}:
                content = body

            response = await self._http_client.request(
                method=request.method,
                url=target_url,
                params=request.query_params,
                headers=headers,
                content=content,
            )

            response_headers = {
                k: v
                for k, v in response.headers.items()
                if not self._is_restricted_header(k)
            }
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
            )
        except ScanUploadProxyException:
            raise
        except asyncio.CancelledError:
            return Response(status_code=499)
        except httpx.TimeoutException:
            return PlainTextResponse("Proxy request timed out.", status_code=504)
        except httpx.HTTPError:
            return PlainTextResponse(
                "An error occurred while processing the request.",
                status_code=500,
            )

    def _resolve_token_provider(self, request: Request) -> TokenProviderProtocol:
        if self._token_provider is not None:
            return self._token_provider

        token_provider = getattr(request.app.state, self._token_provider_state_key, None)
        if token_provider is None:
            raise ScanUploadProxyException(
                f"Token provider not found on app.state.{self._token_provider_state_key}",
                error_code="token_provider_not_configured",
            )
        return token_provider

    def _build_target_url(self, request: Request) -> str:
        base = self._options.target_base_url.rstrip("/")
        if not base:
            raise ScanUploadProxyException(
                "ScanUpload target_base_url is required for API proxying",
                error_code="target_base_url_missing",
            )

        incoming_path = request.url.path
        route_prefix = self._normalize_path(self._options.route_prefix)

        if self._options.strip_route_prefix and route_prefix and incoming_path.startswith(route_prefix):
            incoming_path = incoming_path[len(route_prefix) :]
            if not incoming_path.startswith("/"):
                incoming_path = f"/{incoming_path}"

        return f"{base}{incoming_path}"

    def _build_proxy_headers(self, request: Request) -> dict[str, str]:
        headers_to_forward = {h.lower() for h in self._options.headers_to_forward}
        filtered_headers: dict[str, str] = {}

        # If a whitelist is configured, forward only those headers.
        # Otherwise, forward all non-restricted headers for practical interoperability.
        for key, value in request.headers.items():
            lower_key = key.lower()
            if self._is_restricted_header(key):
                continue

            if headers_to_forward:
                if lower_key in headers_to_forward:
                    filtered_headers[key] = value
            elif lower_key != "authorization":
                filtered_headers[key] = value

        filtered_headers.update(self._options.additional_headers)
        return filtered_headers

    @classmethod
    def _is_restricted_header(cls, header_name: str) -> bool:
        return header_name.lower() in cls._RESTRICTED_HEADERS

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return ""
        normalized = path.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/"
