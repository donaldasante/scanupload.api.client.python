"""Token response model for Keycloak authentication."""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    """Response from Keycloak token endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(default="")
    expires_in: int = Field(default=0)
    refresh_expires_in: int = Field(default=0)
    refresh_token: str | None = Field(default=None)
    token_type: str = Field(default="bearer")
    not_before_policy: int = Field(default=0, alias="not-before-policy")
    session_state: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    error: str | None = Field(default=None)
    error_description: str | None = Field(default=None)
    received_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        """Check if the token response indicates success."""
        return bool(self.access_token and not self.error)

    def is_expired(
        self, early_refresh_seconds: int = 0, now_utc: datetime | None = None
    ) -> bool:
        """Check if the token is expired or within the early refresh window.

        Args:
            early_refresh_seconds: Number of seconds before expiry to consider expired
            now_utc: Current UTC time (defaults to now)

        Returns:
            True if token is expired or within refresh window
        """
        now = now_utc or datetime.now(timezone.utc)
        margin = max(0, early_refresh_seconds)
        expiry = self.received_at_utc + timedelta(seconds=max(0, self.expires_in - margin))
        return now >= expiry

