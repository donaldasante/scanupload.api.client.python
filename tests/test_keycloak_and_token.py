"""Tests for Keycloak client and token management."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from scan_upload_api_client import (
    KeycloakClient,
    KeycloakException,
    ScanUploadOptions,
    TokenProvider,
    TokenResponse,
)
from tests.test_doubles import FakeKeycloakClient, FakeTransport, create_response


def valid_options(**overrides: object) -> ScanUploadOptions:
    """Create valid options for testing."""
    values: dict[str, object] = {
        "keycloak_server_url": "https://kc.local",
        "keycloak_realm": "realm-a",
        "keycloak_client_id": "client-a",
        "keycloak_client_secret": "secret-a",
        "keycloak_timeout": timedelta(seconds=5),
    }
    values.update(overrides)
    return ScanUploadOptions(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_keycloak_client_returns_token_on_success():
    """Test that KeycloakClient returns a token on successful authentication."""
    options = valid_options(keycloak_scope="openid")

    json_data = {"access_token": "abc", "expires_in": 300, "token_type": "bearer"}

    async def handler(request: httpx.Request) -> httpx.Response:
        return create_response(json_data=json_data)

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    sut = KeycloakClient(options, client)
    result = await sut.get_client_credentials_token()

    assert result.access_token == "abc"
    assert result.received_at_utc <= datetime.now(timezone.utc)
    assert transport.last_request is not None
    assert transport.captured_body is not None
    body_str = transport.captured_body.decode()
    assert "grant_type=client_credentials" in body_str
    assert "scope=openid" in body_str

    await sut.close()


@pytest.mark.asyncio
async def test_keycloak_client_throws_on_non_success_status():
    """Test that KeycloakClient raises exception on HTTP error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return create_response(
            status_code=400, json_data={"error": "invalid_client"}
        )

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    sut = KeycloakClient(valid_options(), client)

    with pytest.raises(KeycloakException) as exc_info:
        await sut.get_client_credentials_token()

    assert exc_info.value.error_code == "keycloak_request_failed"
    assert exc_info.value.status_code == 400

    await sut.close()


@pytest.mark.asyncio
async def test_keycloak_client_throws_on_invalid_json():
    """Test that KeycloakClient raises exception on malformed JSON."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return create_response(text="{not-json")

    transport = FakeTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    sut = KeycloakClient(valid_options(), client)

    with pytest.raises(KeycloakException) as exc_info:
        await sut.get_client_credentials_token()

    assert exc_info.value.error_code == "invalid_json"

    await sut.close()


def test_keycloak_client_validates_required_fields():
    """Test that KeycloakClient raises on missing required fields."""
    bad_options = ScanUploadOptions(
        keycloak_server_url="https://kc.local",
        keycloak_realm="",
        keycloak_client_id="client-a",
        keycloak_client_secret="secret-a",
    )
    with pytest.raises(ValueError, match="Keycloak Realm is required"):
        KeycloakClient(bad_options)


@pytest.mark.asyncio
async def test_token_provider_uses_cache_when_valid():
    """Test that TokenProvider caches valid tokens."""
    token = TokenResponse(
        access_token="a", expires_in=3600, received_at_utc=datetime.now(timezone.utc)
    )

    fake = FakeKeycloakClient(lambda: token)
    options = ScanUploadOptions(keycloak_early_refresh_seconds=60)

    sut = TokenProvider(fake, options)

    t1 = await sut.get_access_token()
    t2 = await sut.get_access_token()

    assert t1.access_token == t2.access_token
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_token_provider_refreshes_when_expired():
    """Test that TokenProvider refreshes expired tokens."""
    call_count = 0

    async def factory() -> TokenResponse:
        nonlocal call_count
        call_count += 1
        return TokenResponse(
            access_token=f"token-{call_count}",
            expires_in=1,
            received_at_utc=datetime.now(timezone.utc),
        )

    fake = FakeKeycloakClient(factory)
    options = ScanUploadOptions(keycloak_early_refresh_seconds=120)

    sut = TokenProvider(fake, options)

    first = await sut.get_access_token()
    second = await sut.get_access_token()

    assert first.access_token != second.access_token
    assert fake.calls == 2


def test_token_response_is_expired_and_is_success():
    """Test TokenResponse is_expired and is_success methods."""
    ok = TokenResponse(
        access_token="abc",
        expires_in=300,
        received_at_utc=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )

    assert ok.is_success
    assert not ok.is_expired(0, ok.received_at_utc + timedelta(seconds=299))
    assert ok.is_expired(0, ok.received_at_utc + timedelta(seconds=300))
    assert ok.is_expired(120, ok.received_at_utc + timedelta(seconds=181))

    err = TokenResponse(access_token="abc", error="bad")
    assert not err.is_success


def test_options_keycloak_token_endpoint():
    """Test that token endpoint URL is built correctly."""
    options = ScanUploadOptions(
        keycloak_server_url="https://kc.local/",
        keycloak_realm="realm-a",
    )

    assert (
        options.keycloak_token_endpoint
        == "https://kc.local/realms/realm-a/protocol/openid-connect/token"
    )


def test_options_loads_from_env(monkeypatch: pytest.MonkeyPatch):
    """Test that ScanUploadOptions reads from environment variables."""
    monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://kc.example.com")
    monkeypatch.setenv("KEYCLOAK_REALM", "realm-env")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "client-env")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "secret-env")

    options = ScanUploadOptions()
    assert options.keycloak_server_url == "https://kc.example.com"
    assert options.keycloak_realm == "realm-env"
    assert options.keycloak_client_id == "client-env"
    assert options.keycloak_client_secret == "secret-env"


def test_options_validates_client_id_secret_pair():
    """Test that ScanUploadOptions enforces client id/secret pairing."""
    with pytest.raises(ValueError):
        ScanUploadOptions(
            keycloak_client_id="x",
            keycloak_client_secret="",
        )
    with pytest.raises(ValueError):
        ScanUploadOptions(
            keycloak_client_id="",
            keycloak_client_secret="y",
        )


def test_exception_constructor():
    """Test that KeycloakException constructor sets properties correctly."""
    inner = ValueError("x")
    exc = KeycloakException(
        "message", error_code="code", status_code=401, inner_exception=inner
    )
    assert exc.error_code == "code"
    assert exc.status_code == 401
    assert exc.inner_exception is inner
