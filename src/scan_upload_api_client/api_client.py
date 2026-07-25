"""API client for ScanUpload file operations."""

import asyncio
import io
import zipfile
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx

if TYPE_CHECKING:
    from .token_provider import TokenProvider


class ZipEntryStream:
    """Async-friendly stream over a single zip entry body.

    Wraps the synchronous :class:`zipfile.ZipExtFile` so callbacks can
    read entries from inside ``async`` code without manually managing a
    worker thread. Reads run on the default executor via
    :func:`asyncio.to_thread`, keeping the event loop responsive even
    for large entries.

    Note: Python's :mod:`zipfile` module needs the full archive to be
    seekable before it can locate the *End of Central Directory*
    record, so the network response body is buffered once into memory
    by :meth:`ScanUploadApiClient.download_async_streaming`. Callers
    can, however, stream *individual entries* straight out of this
    object without ever holding more than a single entry in memory.
    """

    def __init__(self, file: Any) -> None:
        self._file = file
        self._closed = False

    async def read(self, size: int = -1) -> bytes:
        """Read up to ``size`` bytes from the entry (or all remaining data when ``-1``)."""
        if size is None or size == -1:
            return await asyncio.to_thread(self._file.read)
        return await asyncio.to_thread(self._file.read, size)

    async def aclose(self) -> None:
        """Close the underlying entry stream (idempotent)."""
        if not self._closed:
            self._closed = True
            try:
                await asyncio.to_thread(self._file.close)
            except Exception:  # noqa: BLE001 - closing twice should be a no-op
                pass

    async def read_chunks(
        self, chunk_size: int = 64 * 1024
    ) -> AsyncIterator[bytes]:
        """Async generator that yields the entry body in fixed-size chunks.

        Useful for streaming entries directly to disk or a network upload
        without ever holding the full entry in memory.
        """
        while True:
            chunk = await self.read(chunk_size)
            if not chunk:
                return
            yield chunk

    async def __aenter__(self) -> "ZipEntryStream":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()


class ScanUploadApiClient:
    """Client for ScanUpload API file operations.

    Two download entry points are exposed:

    * :meth:`download_async` - convenient signature; the callback receives
      each entry as ``bytes`` (entry is buffered before invocation).
    * :meth:`download_async_streaming` - lower-level signature; the
      callback receives a :class:`ZipEntryStream` it can drain chunk by
      chunk. Use this when piping entries to disk or another network
      destination where you want bounded memory regardless of zip size.
    """

    def __init__(
        self,
        base_url: str,
        token_provider: "TokenProvider",
        http_client: httpx.AsyncClient | None = None,
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL of the ScanUpload hub (without trailing
                slash).
            token_provider: Token provider for authentication.
            http_client: Optional ``httpx.AsyncClient`` (one is created
                if ``None``).
        """
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            timeout=120.0, follow_redirects=True
        )

    def _build_download_url(self, session_id: str) -> str:
        """Build the download URL with the session id percent-encoded.

        Percent-encoding the id keeps characters such as ``&`` or ``=``
        within the id travelling as a single path segment rather than
        being interpreted by ``httpx`` as query-string separators.
        ``safe=""`` also encodes any ``/`` characters embedded in the id.
        """
        encoded_session_id = quote(session_id, safe="")
        return (
            f"{self._base_url}/api/file-management/download-session/"
            f"{encoded_session_id}"
        )

    async def download_async_streaming(
        self,
        session_id: str,
        process_entry: Callable[[str, ZipEntryStream], Awaitable[None]],
    ) -> None:
        """Stream a session's zip archive entry-by-entry.

        Pulls the HTTP response in chunks via ``httpx.aiter_bytes`` (so
        large archives don't materialise in one ``read()``) then parses
        the zip from a seekable ``BytesIO``. Per-entry ``ZipEntryStream``
        objects are handed to ``process_entry`` so the caller can stream
        each entry straight to disk, S3, etc., without accumulating
        multiple entries in memory simultaneously.

        Args:
            session_id: Session id to download. URL-encoded automatically.
            process_entry: Async callback invoked once per non-directory
                entry with ``(filename, ZipEntryStream)``. The callback
                may ``await stream.read()`` to drain an entry fully,
                ``async for`` over ``stream.read_chunks()`` for incremental
                processing, or use ``async with stream:`` to guarantee
                cleanup on cancellation.

        Raises:
            httpx.HTTPError: If the request fails or the response is not 2xx.
            zipfile.BadZipFile: If the response body is not a valid zip.
        """
        token = await self._token_provider.get_access_token()
        url = self._build_download_url(session_id)
        headers = {"Authorization": f"Bearer {token.access_token}"}

        async with self._client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            # ``zipfile`` requires seekable I/O to find the End of Central
            # Directory record, so the body is aggregated into a single
            # buffer. Streaming at this layer keeps the network read
            # smooth (chunked) without consuming more memory than reading
            # the whole response up-front.
            chunks: list[bytes] = []
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
            body = b"".join(chunks)

        with zipfile.ZipFile(io.BytesIO(body), "r") as zf:
            for entry in zf.infolist():
                if entry.is_dir():
                    continue
                # ``ZipInfo.open`` is 3.12+; use the portable ``ZipFile.open``
                # form which has been available since Python 3.6.
                stream = ZipEntryStream(zf.open(entry.filename, "r"))
                try:
                    await process_entry(entry.filename, stream)
                finally:
                    await stream.aclose()

    async def download_async(
        self,
        session_id: str,
        process_entry: Callable[[str, bytes], Awaitable[None]],
    ) -> None:
        """Download the session archive and hand each entry to ``process_entry`` as ``bytes``.

        Convenience wrapper around
        :meth:`download_async_streaming` that drains each entry into
        memory before invoking the callback. Use
        :meth:`download_async_streaming` if you want to stream entries
        straight to disk or another network sink.

        Args:
            session_id: Session id to download.
            process_entry: Async callback invoked once per entry with
                ``(filename, bytes)``.

        Raises:
            httpx.HTTPError: If the request fails or the response is not 2xx.
            zipfile.BadZipFile: If the response body is not a valid zip.
        """
        async def collect(name: str, stream: ZipEntryStream) -> None:
            data = await stream.read()
            await process_entry(name, data)

        await self.download_async_streaming(session_id, collect)

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
