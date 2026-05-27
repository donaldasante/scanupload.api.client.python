"""Exception types for ScanUpload API Client."""


class KeycloakException(Exception):
    """Exception raised for Keycloak authentication errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        inner_exception: Exception | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.inner_exception = inner_exception


class ScanUploadProxyException(Exception):
    """Exception raised for ScanUpload proxy errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        status_code: int | None = None,
        inner_exception: Exception | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.inner_exception = inner_exception
