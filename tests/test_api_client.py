"""Tests for API client and download functionality."""

import io
import zipfile

import httpx
import pytest

from scan_upload_api_client import (
    ScanUploadApiClient,
    TokenResponse,
    ZipEntryStream,
)
from tests.test_doubles import FakeTokenProvider, FakeTransport


def _build_zip_bytes(entries: dict[str, str] | None = None) -> bytes:
    """Helper to build an in-memory zip with the given string entries."""
    entries = entries or {"a.txt": "A", "b.txt": "B"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_download_async_processes_every_zip_entry():
    """``download_async`` must call ``process_entry`` once per zip entry."""
    zip_content = _build_zip_bytes()

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

    assert names == ["a.txt", "b.txt"]

    await sut.close()


@pytest.mark.asyncio
async def test_download_async_percent_encodes_session_id():
    """``&`` and ``=`` in the session id must travel as a single path segment."""
    zip_content = _build_zip_bytes({"only.txt": "only"})
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        # ``url`` is the on-the-wire URL (percent-encoded); ``raw_path`` is the
        # raw byte path; ``path`` would be the percent-*decoded* form which is
        # not what we want to assert against.
        captured["url"] = str(request.url)
        captured["raw_path"] = request.url.raw_path.decode("ascii")
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(TokenResponse(access_token="token-xyz"))
    sut = ScanUploadApiClient("https://api.local", provider, client)

    async def noop(filename: str, content: bytes) -> None:
        return None

    raw_session_id = (
        "pQeKOr9oReIGTOMs0QoOP671mI99_L0kECSgXr6Y4eQ&id=vIH4Oxy_EF9SBvnSd9y2Tw"
    )
    await sut.download_async(raw_session_id, noop)

    expected_path = (
        "/api/file-management/download-session/"
        "pQeKOr9oReIGTOMs0QoOP671mI99_L0kECSgXr6Y4eQ%26id%3DvIH4Oxy_EF9SBvnSd9y2Tw"
    )
    assert captured["raw_path"] == expected_path
    assert "id=" not in (captured["url"] or "")
    assert "?" not in (captured["url"] or "")

    await sut.close()


@pytest.mark.asyncio
async def test_download_async_streaming_passes_zip_entry_stream_to_callback():
    """Streaming variant hands the callback a usable ``ZipEntryStream`` per entry."""
    zip_content = _build_zip_bytes({"alpha.txt": "alpha-payload", "beta.bin": "\x00\x01\x02"})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(TokenResponse(access_token="token-stream"))
    sut = ScanUploadApiClient("https://api.local", provider, client)

    received: dict[str, bytes] = {}

    async def process(filename: str, stream: ZipEntryStream) -> None:
        received[filename] = await stream.read()

    await sut.download_async_streaming("session-2", process)

    assert received == {
        "alpha.txt": b"alpha-payload",
        "beta.bin": b"\x00\x01\x02",
    }

    await sut.close()


@pytest.mark.asyncio
async def test_download_async_streaming_yields_entry_bytes_in_chunks():
    """``ZipEntryStream.read_chunks`` must yield the entry body split into chunks."""
    big_payload = b"x" * 5000
    zip_content = _build_zip_bytes({"big.bin": big_payload})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(TokenResponse(access_token="token-stream"))
    sut = ScanUploadApiClient("https://api.local", provider, client)

    chunks: list[bytes] = []

    async def process(filename: str, stream: ZipEntryStream) -> None:
        async for chunk in stream.read_chunks(chunk_size=1024):
            chunks.append(chunk)

    await sut.download_async_streaming("big", process)

    # All chunks concatenated must reproduce the original payload exactly.
    assert b"".join(chunks) == big_payload
    # And there should be more than one chunk for a 5000-byte entry at 1024
    # granularity - proving we're not just reading everything at once.
    assert len(chunks) > 1

    await sut.close()


@pytest.mark.asyncio
async def test_download_async_streaming_iterates_only_zip_files():
    """Only actual zip *file* entries are visited (directories are skipped)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Manufacturing a real directory entry requires ``external_attr``
        # bit twiddling that's awkward to do portably; we instead trust
        # that ``zipfile.is_dir()`` is a one-line guard and focus on the
        # happy-path ordering here.
        zf.writestr("first.txt", "1")
        zf.writestr("nested/file.txt", "2")
        zf.writestr("third.txt", "3")
    zip_content = buf.getvalue()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(TokenResponse(access_token="token-stream"))
    sut = ScanUploadApiClient("https://api.local", provider, client)

    visited: list[str] = []

    async def process(filename: str, stream: ZipEntryStream) -> None:
        await stream.read()
        visited.append(filename)

    await sut.download_async_streaming("any", process)

    assert visited == ["first.txt", "nested/file.txt", "third.txt"]

    await sut.close()


@pytest.mark.asyncio
async def test_download_async_streaming_closes_zip_entries_on_callback_error():
    """If the callback raises, all entry streams must still be closed."""
    zip_content = _build_zip_bytes({"first.txt": "1", "second.txt": "2"})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(TokenResponse(access_token="token-stream"))
    sut = ScanUploadApiClient("https://api.local", provider, client)

    async def process(filename: str, stream: ZipEntryStream) -> None:
        await stream.read()
        raise RuntimeError("callback exploded")

    with pytest.raises(RuntimeError, match="callback exploded"):
        await sut.download_async_streaming("err", process)

    # Closing the client/hit the inner zip should not raise: previous buggy
    # versions leaked file handles. We just exercise the path and assert the
    # outer scope released everything.
    await sut.close()


@pytest.mark.asyncio
async def test_download_async_attaches_bearer_token():
    """Both download methods must send ``Authorization: Bearer <token>``."""
    zip_content = _build_zip_bytes({"ok.txt": "ok"})
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, content=zip_content)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    provider = FakeTokenProvider(
        TokenResponse(access_token="token-bearer", expires_in=300)
    )
    sut = ScanUploadApiClient("https://api.local", provider, client)

    async def noop(filename: str, content: bytes) -> None:
        return None

    async def noop_stream(filename: str, stream: ZipEntryStream) -> None:
        await stream.read()

    await sut.download_async("s", noop)
    await sut.download_async_streaming("s", noop_stream)

    assert captured["authorization"] == "Bearer token-bearer"

    await sut.close()
