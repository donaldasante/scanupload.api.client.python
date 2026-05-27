"""Tests for API client and download functionality."""

import io
import zipfile

import httpx
import pytest

from scan_upload_api_client import ScanUploadApiClient, TokenResponse
from tests.test_doubles import FakeTokenProvider, FakeTransport


@pytest.mark.asyncio
async def test_download_async_processes_every_zip_entry():
    """Test that download_async processes all entries in a zip file."""
    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("a.txt", "A")
        zf.writestr("b.txt", "B")
    zip_content = zip_buffer.getvalue()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(TokenResponse(access_token="token-123"))
    sut = ScanUploadApiClient("https://api.local", provider, client)

    names: list[str] = []

    async def process(filename: str, content: bytes) -> None:
        names.append(filename)

    await sut.download_async("session-1", process)

    assert len(names) == 2
    assert "a.txt" in names
    assert "b.txt" in names

    await sut.close()
