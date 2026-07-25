# ScanUpload API Client - Python

Get a bearer token from [ScanUpload](https://app.scanupload.net/) using a
client ID + secret, then download the files captured for a session.
Two API methods, zero web-framework dependencies.

## Quickstart

1. **Get your client credentials** from the
   [ScanUpload Dashboard](https://app.scanupload.net/dashboard):
   1. Sign in to [app.scanupload.net](https://app.scanupload.net/).
   2. On the dashboard, enter your **company name** and **website URL**, then click **Save**.
   3. Open the **client credentials** section and click **Generate** to mint a client ID + secret.
   4. The dashboard will also show your `KEYCLOAK_SERVER_URL` and `KEYCLOAK_REALM` — copy them too.

2. **Install** the client:

   ```sh
   pip install scan-upload-api-client
   ```

3. **Configure** it (env vars or a `.env` file):

   ```ini
   KEYCLOAK_SERVER_URL=https://identity.scanupload.net/
   KEYCLOAK_REALM=scanupload-hub
   KEYCLOAK_CLIENT_ID=<paste from the dashboard>
   KEYCLOAK_CLIENT_SECRET=<paste from the dashboard>
   HUB_BASE_URL=https://hub.scanupload.net
   ```

4. **Download a session** in 7 lines:

   ```python
   import asyncio
   from scan_upload_api_client import (
       KeycloakClient, ScanUploadApiClient, ScanUploadOptions, TokenProvider,
   )

   async def main():
       opts = ScanUploadOptions()  # reads the KEYCLOAK_* env vars above
       async with KeycloakClient(opts) as kc:
           tp = TokenProvider(kc, opts)
           api = ScanUploadApiClient("https://hub.scanupload.net", tp)
           async def save(name, content):
               open(f"downloads/{name}", "wb").write(content)
           await api.download_async("your-session-id", save)

   asyncio.run(main())
   ```

That's the whole thing. See
[`examples/quickstart.py`](examples/quickstart.py) for the runnable
version.

> **Never commit `KEYCLOAK_CLIENT_SECRET` to source control.** Use a
> secrets manager or your CI/CD provider's secret store.

## Configuration reference

`ScanUploadOptions` reads from environment variables (or `.env`).
Booleans default to `False`, strings default to `""`, durations default
to `timedelta(seconds=60)`, unless noted:

| Field | Env var | Purpose |
| --- | --- | --- |
| `keycloak_server_url` | `KEYCLOAK_SERVER_URL` | Base URL of your Keycloak server |
| `keycloak_realm` | `KEYCLOAK_REALM` | Realm that hosts this client |
| `keycloak_client_id` | `KEYCLOAK_CLIENT_ID` | Client ID for the credentials grant |
| `keycloak_client_secret` | `KEYCLOAK_CLIENT_SECRET` | Client secret for the credentials grant |
| `keycloak_scope` | `KEYCLOAK_SCOPE` | Optional OAuth2 scope (`openid profile email scanupload.hub` works for the hosted SaaS) |
| `keycloak_early_refresh_seconds` | n/a | Refresh margin before token expiry (default `120`) |

To pass values directly instead of from env vars:

```python
options = ScanUploadOptions(
    keycloak_server_url="https://identity.scanupload.net/",
    keycloak_realm="scanupload-hub",
    keycloak_client_id="...",
    keycloak_client_secret="...",
)
```

## Streaming entries straight to disk

If you don't want to buffer each zip entry in memory before writing it,
swap `download_async` for `download_async_streaming`. The callback
receives a `ZipEntryStream` you can drain chunk by chunk:

```python
from scan_upload_api_client import ZipEntryStream

async def stream_to_disk(name: str, entry: ZipEntryStream) -> None:
    with open(f"downloads/{name}", "wb") as fh:
        async for chunk in entry.read_chunks():  # 64 KiB by default
            fh.write(chunk)

await api.download_async_streaming("your-session-id", stream_to_disk)
```

## HTTP integration test (optional)

[`examples/integration_test.py`](examples/integration_test.py) is a
small FastAPI app that hosts the client behind HTTP, mirroring the .NET
`ScanUpload.Api.Client.Test` sample. It exposes `/token`,
`/cached-token`, `/download-file/{session_id}`, `/health`, and `/`
on `http(s)://localhost:7021`. Pre-baked VS Code REST Client scenarios
live in
[`examples/ScanUpload.Api.Client.Test.http`](examples/ScanUpload.Api.Client.Test.http).

```sh
pip install -e .[integration-test]
python examples/integration_test.py
```

## API at a glance

| Symbol | Purpose |
| --- | --- |
| `ScanUploadOptions` | Configuration container |
| `KeycloakClient` | Performs the OAuth2 client-credentials grant |
| `TokenProvider` | Caches tokens and refreshes them on demand |
| `ScanUploadApiClient` | Downloads a session's files |
| `download_async(id, cb)` | cb receives `(name, bytes)` per entry |
| `download_async_streaming(id, cb)` | cb receives `(name, ZipEntryStream)` per entry |
| `ZipEntryStream` | Async-friendly view over a zip entry body |
| `TokenResponse` | OAuth2 token response model |
| `KeycloakException` | Raised for any Keycloak/auth failure |

## Running tests

```sh
pip install -e .[test]
pytest
```

## Compatibility

- Python 3.11+
- Fully async (`httpx.AsyncClient`)
- Thread-safe token caching
- Zero web-framework dependencies — works in FastAPI, Starlette, Django
  async views, Flask, plain asyncio, etc.

## License

See the repository license file for terms.
