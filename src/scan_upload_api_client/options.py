"""Configuration options for ScanUpload API Client."""

from datetime import timedelta
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScanUploadOptions(BaseSettings):
    """Configuration for ScanUpload API client and Keycloak authentication.

    Settings are populated from environment variables (or a ``.env`` file) using
    case-insensitive matching. The expected env var names mirror the field
    names, e.g. ``KEYCLOAK_SERVER_URL``, ``KEYCLOAK_REALM``,
    ``KEYCLOAK_CLIENT_ID``, ``KEYCLOAK_CLIENT_SECRET`` and ``KEYCLOAK_SCOPE``.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Keycloak settings
    keycloak_server_url: str = Field(default="")
    keycloak_realm: str = Field(default="")
    keycloak_client_id: str = Field(default="")
    keycloak_client_secret: str = Field(default="")
    keycloak_scope: str | None = Field(default=None)
    keycloak_timeout: timedelta = Field(default=timedelta(seconds=60))
    keycloak_early_refresh_seconds: int = Field(default=120)

    @property
    def keycloak_token_endpoint(self) -> str:
        """Build the Keycloak token endpoint URL."""
        server = self.keycloak_server_url.rstrip("/")
        return f"{server}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @classmethod
    def from_env(cls) -> "ScanUploadOptions":
        """Load configuration from environment variables."""
        return cls()

    def model_post_init(self, __context: Any) -> None:
        """Validate configuration consistency after initialization."""
        if self.keycloak_client_id and not self.keycloak_client_secret:
            raise ValueError("KeycloakClientSecret is required when KeycloakClientId is set")
        if self.keycloak_client_secret and not self.keycloak_client_id:
            raise ValueError("KeycloakClientId is required when KeycloakClientSecret is set")
