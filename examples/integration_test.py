"""Integration test host for the ScanUpload Python client.

Exposes the three endpoints needed to smoke-test the client against a
real ScanUpload realm during development. It mirrors the
``ScanUpload.Api.Client.Test`` host shipped with the .NET client:

    GET /health
    GET /token              # direct Keycloak call, bypasses cache
    GET /cached-token       # cached token, refreshed only when expired
    GET /download-file/{session_id}  # downloads the session zip bundle

Run it locally:

    pip install -e .[integration-test]
    python examples/integration_test.py

The host binds to ``localhost:7021`` by default to stay consistent with
the .NET sample. Override with ``UVICORN_HOST`` / ``UVICORN_PORT``, and
optionally ``UVICORN_SSL_CERTFILE`` / ``UVICORN_SSL_KEYFILE`` to serve
HTTPS. Configuration is loaded from environment / ``.env`` exactly like
``examples/quickstart.py``.

The matching REST Client scenarios live in
``examples/ScanUpload.Api.Client.Test.http``; open it in VS Code (REST
Client extension) or copy the URLs into curl/Postman.
"""

from __future__ import annotations

import io
import os
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadApiClient,
    ScanUploadOptions,
    TokenProvider,
    TokenResponse,
    ZipEntryStream,
)


def _load_dotenv_values() -> dict[str, str]:
    """Load key/value pairs from the nearest supported ``.env`` file if present."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    values: dict[str, str] = {}

    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def _get_config_value(dotenv_values: dict[str, str], key: str, default: str = "") -> str:
    """Prefer ``.env`` value first, then terminal env var, then default."""
    dotenv_value = dotenv_values.get(key, "").strip()
    if dotenv_value:
        return dotenv_value

    env_value = os.getenv(key, "").strip()
    if env_value:
        return env_value

    return default


def _build_options() -> ScanUploadOptions:
    """Create ScanUpload configuration from ``.env`` and environment variables."""
    dotenv_values = _load_dotenv_values()
    return ScanUploadOptions(
        keycloak_server_url=_get_config_value(
            dotenv_values,
            "KEYCLOAK_SERVER_URL",
            "https://identity.scanupload.net/",
        ),
        keycloak_realm=_get_config_value(
            dotenv_values, "KEYCLOAK_REALM", "scanupload-hub"
        ),
        keycloak_client_id=_get_config_value(dotenv_values, "KEYCLOAK_CLIENT_ID"),
        keycloak_client_secret=_get_config_value(
            dotenv_values, "KEYCLOAK_CLIENT_SECRET"
        ),
        keycloak_scope=_get_config_value(
            dotenv_values,
            "KEYCLOAK_SCOPE",
            "openid profile email scanupload.hub",
        ),
    )


def _token_payload(token: TokenResponse) -> dict[str, object]:
    """Project a ``TokenResponse`` into the JSON shape the test host returns."""
    return {
        "access_token": token.access_token,
        "expires_in": token.expires_in,
        "token_type": token.token_type,
        "scope": token.scope,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise client singletons for the lifetime of the host."""
    options = _build_options()
    dotenv_values = _load_dotenv_values()
    hub_base_url = _get_config_value(
        dotenv_values, "HUB_BASE_URL", "https://hub.scanupload.net"
    )

    keycloak_client = KeycloakClient(options)
    token_provider = TokenProvider(keycloak_client, options)
    api_client = ScanUploadApiClient(
        base_url=hub_base_url,
        token_provider=token_provider,
    )

    app.state.options = options
    app.state.hub_base_url = hub_base_url
    app.state.keycloak_client = keycloak_client
    app.state.token_provider = token_provider
    app.state.api_client = api_client

    try:
        yield
    finally:
        await api_client.close()
        await keycloak_client.close()


app = FastAPI(
    title="ScanUpload Python Client Integration Test",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root(request: Request) -> dict[str, object]:
    """Describe the available endpoints."""
    options: ScanUploadOptions = request.app.state.options
    return {
        "message": "ScanUpload Python client integration test host",
        "keycloak_realm": options.keycloak_realm,
        "endpoints": {
            "health": "/health",
            "direct_token": "/token",
            "cached_token": "/cached-token",
            "download_file": "/download-file/{session_id}",
        },
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for upstream checks."""
    return {"status": "ok"}


@app.get("/token", response_model=None)
async def direct_token(request: Request) -> JSONResponse:
    """Direct Keycloak call - bypasses the ``TokenProvider`` cache."""
    keycloak_client: KeycloakClient = request.app.state.keycloak_client
    try:
        token = await keycloak_client.get_client_credentials_token()
        return JSONResponse(_token_payload(token))
    except Exception as exc:  # noqa: BLE001 - surface as 500
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/cached-token", response_model=None)
async def cached_token(request: Request) -> JSONResponse:
    """Cached token from ``TokenProvider`` - refreshed only when expired."""
    provider: TokenProvider = request.app.state.token_provider
    try:
        token = await provider.get_access_token()
        return JSONResponse(_token_payload(token))
    except Exception as exc:  # noqa: BLE001 - surface as 500
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/download-file/{session_id}")
async def download_file(session_id: str, request: Request) -> Response:
    """Download every file in the session as a single zip archive.

    Demonstrates ``download_async_streaming`` so entries are streamed from
    the hub through ``ZipEntryStream.read_chunks`` rather than buffered
    one entry at a time.
    """
    api_client: ScanUploadApiClient = request.app.state.api_client

    output = io.BytesIO()
    files_received = False
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

        async def collect(filename: str, stream: ZipEntryStream) -> None:
            nonlocal files_received
            # Stream the entry in 64 KiB chunks straight into the output
            # zip instead of materialising it in memory first.
            data = bytearray()
            async for chunk in stream.read_chunks(chunk_size=64 * 1024):
                data.extend(chunk)
            zf.writestr(filename, bytes(data))
            files_received = True

        try:
            await api_client.download_async_streaming(session_id, collect)
        except Exception as exc:  # noqa: BLE001 - surface as bad gateway
            raise HTTPException(
                status_code=502,
                detail=f"Failed to download from ScanUpload hub: {exc}",
            ) from exc

    if not files_received:
        raise HTTPException(
            status_code=404,
            detail="No files found for this session.",
        )

    output.seek(0)
    return Response(
        content=output.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{session_id}.zip"',
        },
    )


def _uvicorn_run_kwargs() -> dict[str, object]:
    """Build uvicorn configuration from environment variables."""
    run_kwargs: dict[str, object] = {
        "host": os.getenv("UVICORN_HOST", "localhost"),
        "port": int(os.getenv("UVICORN_PORT", "7021")),
    }

    ssl_certfile = os.getenv("UVICORN_SSL_CERTFILE")
    ssl_keyfile = os.getenv("UVICORN_SSL_KEYFILE")
    if ssl_certfile and ssl_keyfile:
        run_kwargs["ssl_certfile"] = ssl_certfile
        run_kwargs["ssl_keyfile"] = ssl_keyfile

    return run_kwargs


if __name__ == "__main__":
    import uvicorn

    # Pass the app object directly - the ``examples`` folder is not a
    # proper Python package (no ``__init__.py``), so the dotted
    # ``"examples.integration_test:app"`` string would fail to resolve.
    uvicorn.run(app, **_uvicorn_run_kwargs())
