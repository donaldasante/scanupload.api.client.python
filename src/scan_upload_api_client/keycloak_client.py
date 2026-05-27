"""Keycloak client for authentication."""

import json
from typing import Any

import httpx

from .exceptions import KeycloakException
from .options import ScanUploadProxyOptions
from .token_response import TokenResponse


class KeycloakClient:
    """Client for Keycloak authentication using client credentials flow."""

    def __init__(
        self,
        options: ScanUploadProxyOptions,
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize the Keycloak client.

        Args:
            options: Configuration options
            http_client: Optional HTTP client (if None, creates a new one)
        """
        self._options = options
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=options.keycloak_timeout.total_seconds()
        )
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Validate that required configuration is present."""
        if not self._options.keycloak_server_url:
            raise ValueError("Keycloak ServerUrl is required")
        if not self._options.keycloak_realm:
            raise ValueError("Keycloak Realm is required")
        if not self._options.keycloak_client_id:
            raise ValueError("Keycloak ClientId is required")
        if not self._options.keycloak_client_secret:
            raise ValueError("Keycloak ClientSecret is required")

    async def get_client_credentials_token(self) -> TokenResponse:
        """Request an access token using client credentials grant.

        Returns:
            TokenResponse with access token and metadata

        Raises:
            KeycloakException: If the request fails
        """
        form_data = {
            "grant_type": "client_credentials",
            "client_id": self._options.keycloak_client_id,
            "client_secret": self._options.keycloak_client_secret,
        }

        if self._options.keycloak_scope:
            form_data["scope"] = self._options.keycloak_scope

        try:
            response = await self._client.post(
                self._options.keycloak_token_endpoint,
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            response_text = response.text

            if not response.is_success:
                raise KeycloakException(
                    message=f"Keycloak request failed with status {response.status_code}: {response_text}",
                    error_code="keycloak_request_failed",
                    status_code=response.status_code,
                )

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                raise KeycloakException(
                    message="Failed to parse Keycloak response",
                    error_code="invalid_json",
                    inner_exception=e,
                ) from e

            token_response = TokenResponse(**data)

            if not token_response.access_token:
                raise KeycloakException(
                    message="Failed to deserialize token response",
                    error_code="invalid_response",
                )

            if not token_response.is_success:
                raise KeycloakException(
                    message=token_response.error_description or "Token request failed",
                    error_code=token_response.error or "unknown_error",
                )

            return token_response

        except httpx.HTTPError as e:
            raise KeycloakException(
                message="HTTP request to Keycloak failed",
                error_code="http_request_failed",
                inner_exception=e,
            ) from e
        except httpx.TimeoutException as e:
            raise KeycloakException(
                message="Request to Keycloak timed out",
                error_code="request_timeout",
                inner_exception=e,
            ) from e

    async def __aenter__(self) -> "KeycloakClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client if owned by this instance."""
        if self._owns_client:
            await self._client.aclose()
