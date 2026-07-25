"""ScanUpload API Client for Python.

This package provides Python bindings for the ScanUpload API:
- Client-credentials authentication against Keycloak
- Cached bearer token acquisition
- File download from a ScanUpload session

The bearer tokens obtained via ``KeycloakClient``/``TokenProvider`` are only
authorised for the ``download-session`` endpoint - no other endpoint is
exposed by this client.
"""

from .api_client import ScanUploadApiClient, ZipEntryStream
from .exceptions import KeycloakException
from .keycloak_client import KeycloakClient
from .options import ScanUploadOptions
from .token_provider import TokenProvider
from .token_response import TokenResponse

__version__ = "1.0.0"
__all__ = [
    "KeycloakException",
    "KeycloakClient",
    "ScanUploadOptions",
    "TokenProvider",
    "TokenResponse",
    "ScanUploadApiClient",
    "ZipEntryStream",
]
