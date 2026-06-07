"""Reusable FastAPI example built on the published ScanUpload client package."""

import io
import os
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response

from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadApiClient,
    ScanUploadProxyOptions,
    TokenProvider,
)
from scan_upload_api_client.middleware import ScanUploadProxyMiddleware


def _load_dotenv_values() -> dict[str, str]:
    """Load key/value pairs from the nearest supported .env file if present."""
    values: dict[str, str] = {}
    candidate_paths: list[Path] = []
    override_path = os.getenv("SCANUPLOAD_DOTENV_PATH", "").strip()

    if override_path:
        candidate_paths.append(Path(override_path).expanduser())

    candidate_paths.append(Path.cwd() / ".env")
    candidate_paths.append(Path(__file__).resolve().parents[1] / ".env")

    seen_paths: set[Path] = set()
    for env_path in candidate_paths:
        resolved_path = env_path.resolve()
        if resolved_path in seen_paths or not resolved_path.exists():
            continue

        seen_paths.add(resolved_path)
        for raw_line in resolved_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

        break

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

def _build_options() -> ScanUploadProxyOptions:
    """Create ScanUpload configuration from .env and environment variables."""
    dotenv_values = _load_dotenv_values()
    return ScanUploadProxyOptions(
        target_base_url=_get_config_value(
            dotenv_values,
            "SCANUPLOAD_TARGET_BASE_URL",
            "https://hub.scanupload.net/api/front-end",
        ),
        route_prefix=_get_config_value(
            dotenv_values,
            "SCANUPLOAD_ROUTE_PREFIX",
            "/scanupload-api",
        ),
        token_route=_get_config_value(
            dotenv_values,
            "SCANUPLOAD_TOKEN_ROUTE",
            "/scanupload-api/token",
        ),
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
        keycloak_realm=_get_config_value(
            dotenv_values,
            "KEYCLOAK_REALM",
            "scanupload-hub",
        ),
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


def _require_token_provider(request: Request) -> TokenProvider:
    token_provider = getattr(request.app.state, "scan_upload_token_provider", None)
    if token_provider is None:
        raise HTTPException(status_code=500, detail="Token provider not initialized")
    return token_provider


def _require_api_client(request: Request) -> ScanUploadApiClient:
    api_client = getattr(request.app.state, "scan_upload_api_client", None)
    if api_client is None:
        raise HTTPException(status_code=500, detail="API client not initialized")
    return api_client


def create_app(options: ScanUploadProxyOptions | None = None) -> FastAPI:
    """Create a FastAPI app that uses the published ScanUpload package."""
    app_options = options or _build_options()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        keycloak_client = KeycloakClient(app_options)
        token_provider = TokenProvider(keycloak_client, app_options)
        api_client = ScanUploadApiClient(
            base_url=app_options.api_client_base_url,
            token_provider=token_provider,
        )
        app.state.scan_upload_keycloak_client = keycloak_client
        app.state.scan_upload_token_provider = token_provider
        app.state.scan_upload_api_client = api_client

        try:
            yield
        finally:
            await api_client.close()
            await keycloak_client.close()

    app = FastAPI(title="ScanUpload FastAPI Example", lifespan=lifespan)
    app.state.scan_upload_options = app_options
    app.add_middleware(ScanUploadProxyMiddleware, options=app_options)
    return app


app = create_app()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ScanUpload FastAPI example",
        "token_route": "/token",
        "download_route": "/download/{session_id}",
        "proxy_prefix": app.state.scan_upload_options.route_prefix,
    }


@app.get("/health")
async def health():
    """Health endpoint for app readiness checks."""
    return {"status": "ok"}


@app.get("/token")
async def get_token(request: Request):
    """Get an access token."""
    try:
        token = await _require_token_provider(request).get_access_token()
        return {
            "access_token": token.access_token,
            "expires_in": token.expires_in,
            "token_type": token.token_type,
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@app.get("/download-file/{session_id}")
async def download_session(session_id: str, request: Request):
    api_client: ScanUploadApiClient = _require_api_client(request)

    output = io.BytesIO()
    files_received = False

    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        async def collect_file(filename: str, content: bytes) -> None:
            nonlocal files_received
            zf.writestr(filename, content)
            files_received = True

        try:
            await api_client.download_async(session_id, collect_file)
        except Exception as exc:
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


if __name__ == "__main__":
    import uvicorn

    dotenv_values = _load_dotenv_values()
    ssl_certfile = _get_config_value(dotenv_values, "UVICORN_SSL_CERTFILE")
    ssl_keyfile = _get_config_value(dotenv_values, "UVICORN_SSL_KEYFILE")

    run_kwargs = {
        "host": _get_config_value(dotenv_values, "UVICORN_HOST", "localhost"),
        "port": int(_get_config_value(dotenv_values, "UVICORN_PORT", "7021")),
    }
    if ssl_certfile and ssl_keyfile:
        run_kwargs["ssl_certfile"] = ssl_certfile
        run_kwargs["ssl_keyfile"] = ssl_keyfile

    uvicorn.run(app, **run_kwargs)
