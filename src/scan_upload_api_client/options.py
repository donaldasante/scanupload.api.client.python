"""Configuration options for ScanUpload API Client."""

from datetime import timedelta
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScanUploadProxyOptions(BaseSettings):
    """Configuration for ScanUpload proxy and API client."""

    model_config = SettingsConfigDict(
        env_prefix="SCANUPLOAD_",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    # Proxy settings
    target_base_url: str = Field(
        default="", alias="ScanUploadTargetBaseUrl", validation_alias="target_base_url"
    )
    route_prefix: str = Field(
        default="", alias="ScanUploadRoutePrefix", validation_alias="route_prefix"
    )
    token_route: str = Field(
        default="", alias="ScanUploadTokenRoute", validation_alias="token_route"
    )
    strip_route_prefix: bool = Field(
        default=False,
        alias="ScanUploadStripRoutePrefix",
        validation_alias="strip_route_prefix",
    )
    request_timeout: timedelta = Field(
        default=timedelta(minutes=1),
        alias="ScanUploadRequestTimeout",
        validation_alias="request_timeout",
    )

    # Headers
    headers_to_forward: list[str] = Field(
        default_factory=list,
        alias="ScanUploadHeadersToForward",
        validation_alias="headers_to_forward",
    )
    additional_headers: dict[str, str] = Field(
        default_factory=dict,
        alias="ScanUploadAdditionalHeaders",
        validation_alias="additional_headers",
    )

    # API Client settings
    api_client_base_url: str = Field(
        default="",
        alias="ScanUploadApiClientBaseUrl",
        validation_alias="api_client_base_url",
    )

    # Keycloak settings
    keycloak_server_url: str = Field(
        default="", alias="KeycloakServerUrl", validation_alias="keycloak_server_url"
    )
    keycloak_realm: str = Field(
        default="", alias="KeycloakRealm", validation_alias="keycloak_realm"
    )
    keycloak_client_id: str = Field(
        default="", alias="KeycloakClientId", validation_alias="keycloak_client_id"
    )
    keycloak_client_secret: str = Field(
        default="", alias="KeycloakClientSecret", validation_alias="keycloak_client_secret"
    )
    keycloak_scope: str | None = Field(
        default=None, alias="KeycloakScope", validation_alias="keycloak_scope"
    )
    keycloak_timeout: timedelta = Field(
        default=timedelta(seconds=60),
        alias="KeycloakTimeout",
        validation_alias="keycloak_timeout",
    )
    keycloak_early_refresh_seconds: int = Field(
        default=120,
        alias="KeycloakEarlyRefreshSeconds",
        validation_alias="keycloak_early_refresh_seconds",
    )

    @property
    def keycloak_token_endpoint(self) -> str:
        """Build the Keycloak token endpoint URL."""
        server = self.keycloak_server_url.rstrip("/")
        return f"{server}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @classmethod
    def from_env(cls) -> "ScanUploadProxyOptions":
        """Load configuration from environment variables."""
        return cls()

    def model_post_init(self, __context: Any) -> None:
        """Validate configuration consistency after initialization."""
        # The token endpoint can be computed with only server URL + realm.
        # Client credentials are validated by KeycloakClient at usage time.
        if self.keycloak_client_id and not self.keycloak_client_secret:
            raise ValueError("KeycloakClientSecret is required when KeycloakClientId is set")
        if self.keycloak_client_secret and not self.keycloak_client_id:
            raise ValueError("KeycloakClientId is required when KeycloakClientSecret is set")
