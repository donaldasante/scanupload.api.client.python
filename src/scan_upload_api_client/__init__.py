"""ScanUpload API Client for Python.

This package provides Python bindings for the ScanUpload API, including:
- Keycloak authentication and token management
- API client for file downloads
- Proxy service for web frameworks
"""

from .exceptions import KeycloakException, ScanUploadProxyException
from .keycloak_client import KeycloakClient
from .options import ScanUploadProxyOptions
from .token_provider import TokenProvider
from .token_response import TokenResponse
from .api_client import ScanUploadApiClient

__version__ = "0.1.0a3"
__all__ = [
    "KeycloakException",
    "ScanUploadProxyException",
    "KeycloakClient",
    "ScanUploadProxyOptions",
    "TokenProvider",
    "TokenResponse",
    "ScanUploadApiClient",
]
