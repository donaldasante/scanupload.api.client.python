"""FastAPI example with ScanUpload proxy middleware."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadApiClient,
    ScanUploadProxyOptions,
    TokenProvider,
)
from scan_upload_api_client.middleware import ScanUploadProxyMiddleware


def _load_dotenv_values() -> dict[str, str]:
    """Load key/value pairs from project .env file if present."""
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
    """Prefer .env value first, then terminal environment variable, then default."""
    dotenv_value = dotenv_values.get(key, "").strip()
    if dotenv_value:
        return dotenv_value

    env_value = os.getenv(key, "").strip()
    if env_value:
        return env_value

    return default

# Load configuration from .env first, then environment variables.
dotenv_values = _load_dotenv_values()
options = ScanUploadProxyOptions(
    target_base_url=_get_config_value(
        dotenv_values,
        "SCANUPLOAD_TARGET_BASE_URL",
        "https://hub.scanupload.net/api/front-end",
    ),
    route_prefix=_get_config_value(dotenv_values, "SCANUPLOAD_ROUTE_PREFIX", "/scanupload-api"),
    token_route=_get_config_value(dotenv_values, "SCANUPLOAD_TOKEN_ROUTE", "/scanupload-api/token"),
    strip_route_prefix=_get_config_value(
        dotenv_values,
        "SCANUPLOAD_STRIP_ROUTE_PREFIX",
        "true",
    ).lower()
    in {"1", "true", "yes", "on"},
    keycloak_server_url=_get_config_value(
        dotenv_values,
        "KEYCLOAK_SERVER_URL",
        "https://identity.scanupload.net/",
    ),
    keycloak_realm=_get_config_value(dotenv_values, "KEYCLOAK_REALM", "scanupload-hub"),
    keycloak_client_id=_get_config_value(dotenv_values, "KEYCLOAK_CLIENT_ID"),
    keycloak_client_secret=_get_config_value(dotenv_values, "KEYCLOAK_CLIENT_SECRET"),
    keycloak_scope=_get_config_value(
        dotenv_values,
        "KEYCLOAK_SCOPE",
        "openid profile email scanupload.hub",
    ),
    api_client_base_url=_get_config_value(
        dotenv_values,
        "SCANUPLOAD_API_CLIENT_BASE_URL",
        "https://hub.scanupload.net",
    ),
)

# Global state (in production, use dependency injection)
_keycloak_client: KeycloakClient | None = None
_token_provider: TokenProvider | None = None
_api_client: ScanUploadApiClient | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize and clean up clients for the app lifecycle."""
    global _keycloak_client, _token_provider, _api_client

    _keycloak_client = KeycloakClient(options)
    _token_provider = TokenProvider(_keycloak_client, options)
    _api_client = ScanUploadApiClient(
        base_url=options.api_client_base_url,
        token_provider=_token_provider,
    )
    _app.state.scan_upload_token_provider = _token_provider

    try:
        yield
    finally:
        if _api_client:
            await _api_client.close()
        if _keycloak_client:
            await _keycloak_client.close()


# Create FastAPI app
app = FastAPI(title="ScanUpload FastAPI Example", lifespan=lifespan)
app.add_middleware(ScanUploadProxyMiddleware, options=options)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "ScanUpload FastAPI example"}


@app.get("/token")
async def get_token():
    """Get an access token."""
    if not _token_provider:
        raise HTTPException(status_code=500, detail="Token provider not initialized")

    try:
        token = await _token_provider.get_access_token()
        return {
            "access_token": token.access_token,
            "expires_in": token.expires_in,
            "token_type": token.token_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{session_id}")
async def download_session(session_id: str):
    """Download files from a session."""
    if not _api_client:
        raise HTTPException(status_code=500, detail="API client not initialized")

    try:
        files = []

        async def process_file(filename: str, content: bytes):
            files.append({"filename": filename, "size": len(content)})

        await _api_client.download_async(session_id, process_file)

        return {"session_id": session_id, "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    ssl_certfile = _get_config_value(dotenv_values, "UVICORN_SSL_CERTFILE")
    ssl_keyfile = _get_config_value(dotenv_values, "UVICORN_SSL_KEYFILE")

    run_kwargs = {
        "host": "localhost",
        "port": 7021,
    }
    if ssl_certfile and ssl_keyfile:
        run_kwargs["ssl_certfile"] = ssl_certfile
        run_kwargs["ssl_keyfile"] = ssl_keyfile

    uvicorn.run(app, **run_kwargs)
