"""API client for ScanUpload file operations."""

import io
import zipfile
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .token_provider import TokenProvider


class ScanUploadApiClient:
    """Client for ScanUpload API file operations."""

    def __init__(
        self,
        base_url: str,
        token_provider: "TokenProvider",
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL for the API
            token_provider: Token provider for authentication
            http_client: Optional HTTP client (creates new one if None)
        """
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=120.0, follow_redirects=True
        )

    async def download_async(
        self,
        session_id: str,
        process_entry: Callable[[str, bytes], Awaitable[None]],
    ) -> None:
        """Download and process a zip archive from a session.

        Args:
            session_id: Session ID to download
            process_entry: Async callback to process each file (filename, content)

        Raises:
            httpx.HTTPError: If the download fails
        """
        token = await self._token_provider.get_access_token()

        url = f"{self._base_url}/api/file-management/download-session/{session_id}"

        response = await self._client.get(
            url,
            headers={"Authorization": f"Bearer {token.access_token}"},
        )
        response.raise_for_status()

        # Read zip content into memory
        zip_content = await response.aread()

        # Process zip entries
        with zipfile.ZipFile(io.BytesIO(zip_content), "r") as zip_file:
            for entry in zip_file.infolist():
                if not entry.is_dir():
                    content = zip_file.read(entry.filename)
                    await process_entry(entry.filename, content)

    async def close(self) -> None:
        """Close the HTTP client if owned by this instance."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "ScanUploadApiClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()
