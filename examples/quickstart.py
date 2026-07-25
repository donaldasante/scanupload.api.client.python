"""Quick start example for the ScanUpload API client.

This script demonstrates the only workflow supported by the client:

1. Use ``KeycloakClient`` + ``TokenProvider`` to obtain a cached bearer token
   from your ScanUpload realm using the client credentials grant.
2. Use ``ScanUploadApiClient`` to download the files for a given session.

The bearer token is only authorised for the ``download-session`` endpoint;
this client does not expose any other ScanUpload endpoints.
"""

import asyncio
import os
from pathlib import Path

from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadApiClient,
    ScanUploadOptions,
    TokenProvider,
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


async def main() -> None:
    """Demonstrate token acquisition and a session download."""
    dotenv_values = _load_dotenv_values()

    options = ScanUploadOptions(
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

    async with KeycloakClient(options) as keycloak_client:
        token_provider = TokenProvider(keycloak_client, options)

        # First call fetches token; subsequent calls reuse the cache.
        token = await token_provider.get_access_token()
        print(f"[OK] Got access token (expires in {token.expires_in}s)")

        session_id = _get_config_value(dotenv_values, "SESSION_ID")
        if not session_id:
            print(
                "[INFO] Set SESSION_ID in your environment or .env to download files."
            )
            await token_provider.close()
            await keycloak_client.close()
            return

        api_client = ScanUploadApiClient(
            base_url=_get_config_value(
                dotenv_values, "HUB_BASE_URL", "https://hub.scanupload.net"
            ),
            token_provider=token_provider,
        )

        print(f"\nDownloading files from session: {session_id}")

        async def process_file(filename: str, content: bytes) -> None:
            print(f"  - {filename}: {len(content)} bytes")
            output_path = f"downloads/{filename}"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as handle:
                handle.write(content)

        await api_client.download_async(session_id, process_file)
        print("[OK] Download complete")

        await api_client.close()
        await token_provider.close()


if __name__ == "__main__":
    asyncio.run(main())
