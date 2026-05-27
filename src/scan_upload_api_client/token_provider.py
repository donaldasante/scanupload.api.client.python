"""Token provider with caching and automatic refresh."""

import asyncio
from typing import TYPE_CHECKING

from .options import ScanUploadProxyOptions
from .token_response import TokenResponse

if TYPE_CHECKING:
    from .keycloak_client import KeycloakClient


class TokenProvider:
    """Provides cached access tokens with automatic refresh."""

    def __init__(self, keycloak_client: "KeycloakClient", options: ScanUploadProxyOptions):
        """Initialize the token provider.

        Args:
            keycloak_client: Keycloak client for token acquisition
            options: Configuration options
        """
        self._keycloak_client = keycloak_client
        self._options = options
        self._cached: TokenResponse | None = None
        self._refresh_lock = asyncio.Lock()

    async def get_access_token(self) -> TokenResponse:
        """Get an access token, using cache if valid or refreshing if needed.

        Returns:
            TokenResponse with valid access token

        Raises:
            KeycloakException: If token acquisition fails
        """
        # Fast path: check cached token without lock
        current = self._cached
        if current and not current.is_expired(self._options.keycloak_early_refresh_seconds):
            return current

        # Slow path: acquire lock and refresh
        async with self._refresh_lock:
            # Double-check after acquiring lock
            current = self._cached
            if current and not current.is_expired(
                self._options.keycloak_early_refresh_seconds
            ):
                return current

            # Refresh token
            self._cached = await self._keycloak_client.get_client_credentials_token()
            return self._cached

    async def close(self) -> None:
        """Clean up resources (lock cleanup not needed in Python)."""
        pass
