"""Quick start example for ScanUpload API Client."""

import asyncio
import os
from pathlib import Path

from scan_upload_api_client import (
    KeycloakClient,
    ScanUploadApiClient,
    ScanUploadProxyOptions,
    TokenProvider,
)


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


async def main():
    """Demonstrate basic usage of the ScanUpload API Client."""

    # Load configuration from .env first, then fall back to environment variables.
    dotenv_values = _load_dotenv_values()
    options = ScanUploadProxyOptions(
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

    # Create Keycloak client and token provider
    async with KeycloakClient(options) as keycloak_client:
        token_provider = TokenProvider(keycloak_client, options)

        # Get a token (will be cached)
        token = await token_provider.get_access_token()
        print(f"[OK] Got access token (expires in {token.expires_in}s)")

        # Create API client
        api_client = ScanUploadApiClient(
            base_url=options.api_client_base_url,
            token_provider=token_provider,
        )

        # Example: Download files from a session
        session_id = _get_config_value(dotenv_values, "SESSION_ID")
        if session_id:
            print(f"\nDownloading files from session: {session_id}")

            async def process_file(filename: str, content: bytes):
                print(f"  - {filename}: {len(content)} bytes")
                # Save to disk or process as needed
                output_path = f"downloads/{filename}"
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(content)

            await api_client.download_async(session_id, process_file)
            print("[OK] Download complete")

        await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
