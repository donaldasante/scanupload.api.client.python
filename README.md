# ScanUpload API Client - Python Integration Guide

[ScanUpload](https://app.scanupload.net/) enables the integration and the
ability to use QR codes to scan and upload files directly from a mobile device
to your webapp.

This guide explains how to integrate **scan-upload-api-client** into a Python
application. The client library requires **Python 3.11+** and is compatible
with:

- FastAPI
- Starlette
- Django (with async views)
- Flask (with async support)
- Any ASGI application

## Prerequisites

- Python 3.11+
- [A ScanUpload account](https://app.scanupload.net/)
- A ScanUpload **Client ID** and **Client Secret**

## Installation

```sh
pip install scan-upload-api-client
```

If you want to pin to a specific release:

```sh
pip install scan-upload-api-client==1.0.0
```

For ASGI/web framework integration:

```sh
pip install scan-upload-api-client[asgi]
```

## Configuration

Configure using environment variables or a `.env` file:

```ini
SCANUPLOAD_TARGET_BASE_URL=https://hub.scanupload.net/api/front-end
SCANUPLOAD_ROUTE_PREFIX=/scanupload-api
SCANUPLOAD_TOKEN_ROUTE=/scanupload-api/token
SCANUPLOAD_STRIP_ROUTE_PREFIX=true
SCANUPLOAD_REQUEST_TIMEOUT=90

SCANUPLOAD_API_CLIENT_BASE_URL=https://hub.scanupload.net

KEYCLOAK_SERVER_URL=https://identity.scanupload.net/
KEYCLOAK_REALM=scanupload-hub
KEYCLOAK_CLIENT_ID=your-client-id
KEYCLOAK_CLIENT_SECRET=your-client-secret
KEYCLOAK_SCOPE=openid profile email scanupload.hub

# Optional: enable HTTPS for FastAPI example
UVICORN_SSL_CERTFILE=C:/path/to/localhost.pem
UVICORN_SSL_KEYFILE=C:/path/to/localhost-key.pem
```

The example apps in `examples/` load configuration in this order:

1. `SCANUPLOAD_DOTENV_PATH` (if set)
2. `.env` in the current working directory
3. `.env` in the repository root
4. Terminal environment variables

WARNING: **Never commit secrets to source control.** Use environment variables
or a secrets management system.

## Basic Usage

### Keycloak Token Client

```python
import asyncio
from scan_upload_api_client import KeycloakClient, ScanUploadProxyOptions

async def main():
    options = ScanUploadProxyOptions(
        keycloak_server_url="https://identity.scanupload.net/",
        keycloak_realm="scanupload-hub",
        keycloak_client_id="your-client-id",
        keycloak_client_secret="your-client-secret",
    )

    async with KeycloakClient(options) as client:
        token = await client.get_client_credentials_token()
        print(f"Access token: {token.access_token}")

asyncio.run(main())
```

### Token Provider with Caching

```python
from scan_upload_api_client import TokenProvider, KeycloakClient, ScanUploadProxyOptions

async def main():
    options = ScanUploadProxyOptions(
        keycloak_server_url="https://identity.scanupload.net/",
        keycloak_realm="scanupload-hub",
        keycloak_client_id="your-client-id",
        keycloak_client_secret="your-client-secret",
        keycloak_early_refresh_seconds=120,
    )

    async with KeycloakClient(options) as keycloak_client:
        provider = TokenProvider(keycloak_client, options)

        # First call fetches token
        token1 = await provider.get_access_token()

        # Second call uses cache
        token2 = await provider.get_access_token()

        assert token1.access_token == token2.access_token

asyncio.run(main())
```

### Download Files

```python
from scan_upload_api_client import ScanUploadApiClient, TokenProvider

async def main():
    # Setup token provider...
    api_client = ScanUploadApiClient(
        base_url="https://hub.scanupload.net",
        token_provider=provider,
    )

    async def process_file(filename: str, content: bytes):
        print(f"Processing {filename} ({len(content)} bytes)")
        # Save or process file content

    await api_client.download_async("session-id-123", process_file)

asyncio.run(main())
```

## Framework Integration

If you are consuming the package from PyPI, install the ASGI extras first:

```sh
pip install "scan-upload-api-client[asgi]"
```

Then create your FastAPI app with the published package:

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadProxyOptions,
    TokenProvider,
)
from scan_upload_api_client.middleware import ScanUploadProxyMiddleware

options = ScanUploadProxyOptions(
    target_base_url="https://hub.scanupload.net/api/front-end",
    route_prefix="/scanupload-api",
    token_route="/scanupload-api/token",
    strip_route_prefix=True,
    keycloak_server_url="https://identity.scanupload.net/",
    keycloak_realm="scanupload-hub",
    keycloak_client_id="your-client-id",
    keycloak_client_secret="your-client-secret",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    keycloak_client = KeycloakClient(options)
    token_provider = TokenProvider(keycloak_client, options)
    app.state.scan_upload_token_provider = token_provider
    try:
        yield
    finally:
        await keycloak_client.close()

app = FastAPI(title="ScanUpload FastAPI Example", lifespan=lifespan)
app.add_middleware(ScanUploadProxyMiddleware, options=options)

@app.get("/")
async def root():
    return {"message": "ScanUpload API client is active"}
```

The reusable repository example in
[examples/fastapi_example.py](examples/fastapi_example.py) follows the same
pattern, adds `/health`, `/token`, and `/download-file/{session_id}` helper
routes (the download route returns all session files as a zip archive), and can
be adapted directly into an existing FastAPI service.

You can also integrate the middleware in Starlette:

```python
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadProxyOptions,
    TokenProvider,
)
from scan_upload_api_client.middleware import ScanUploadProxyMiddleware

options = ScanUploadProxyOptions(
    target_base_url="https://hub.scanupload.net/api/front-end",
    route_prefix="/scanupload-api",
    token_route="/scanupload-api/token",
    strip_route_prefix=True,
    keycloak_server_url="https://identity.scanupload.net/",
    keycloak_realm="scanupload-hub",
    keycloak_client_id="your-client-id",
    keycloak_client_secret="your-client-secret",
)

async def root(_):
    return JSONResponse({"message": "ScanUpload API client is active"})

@asynccontextmanager
async def lifespan(app: Starlette):
    keycloak_client = KeycloakClient(options)
    token_provider = TokenProvider(keycloak_client, options)
    app.state.scan_upload_token_provider = token_provider
    try:
        yield
    finally:
        await keycloak_client.close()

app = Starlette(routes=[Route("/", root)], lifespan=lifespan)
app.add_middleware(ScanUploadProxyMiddleware, options=options)
```

The reusable repository example in
[examples/starlette_example.py](examples/starlette_example.py) follows the same
pattern, adds `/health`, `/token`, and `/download-file/{session_id}` helper
routes (the download route returns all session files as a zip archive), and can
be adapted directly into an existing Starlette service.

To run the full FastAPI example app from this repository:

```sh
pip install -e .[asgi]
python examples/fastapi_example.py
```

To run the full Starlette example app from this repository:

```sh
pip install -e .[asgi]
python examples/starlette_example.py
```

By default, the example runs on `http://localhost:7021`. If both
`UVICORN_SSL_CERTFILE` and `UVICORN_SSL_KEYFILE` are set, it runs on
`https://localhost:7021`.

## Running Tests

```sh
# Install test dependencies
pip install -e .[test]

# Run tests
pytest
```

## Compatibility Notes

- Requires Python 3.11+
- Fully async (uses `httpx.AsyncClient`)
- Thread-safe token caching
- Compatible with FastAPI, Starlette, Django, Flask

## License

See the repository license file for terms.
