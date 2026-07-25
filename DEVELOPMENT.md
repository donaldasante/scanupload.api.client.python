# Python Development Setup

## Prerequisites

- Python 3.11 or higher
- pip

## Setup

1. Create a virtual environment:

```bash
python -m venv venv
```

2. Activate the virtual environment:

**Windows:**

```cmd
venv\Scripts\activate
```

**Linux/Mac:**

```bash
source venv/bin/activate
```

3. Install the package in editable mode with test dependencies:

```bash
pip install -e .[test]
```

The example script in `examples/` reads values from `.env` first, then
falls back to environment variables using the precedence in
[python-dotenv](https://pypi.org/project/python-dotenv/):

1. `KEYCLOAK_*` environment variables (or whatever you set in
   `ScanUploadOptions`)
2. Terminal environment variables
3. Built-in defaults from `examples/quickstart.py`

## Run the quickstart example

Copy `.env.example` to `.env` and populate the Keycloak values provided
by your ScanUpload administrator, then:

```bash
SESSION_ID=<your session id> python examples/quickstart.py
```

The script prints each downloaded file to stdout and writes the contents
under `downloads/`.

## Run the integration test host

[`examples/integration_test.py`](examples/integration_test.py) is a
small FastAPI app that hosts the client behind HTTP, mirroring the
`ScanUpload.Api.Client.Test` sample from the .NET SDK. It exposes:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | Endpoint catalogue (returns the configured Keycloak realm too) |
| `GET` | `/health` | Liveness probe |
| `GET` | `/token` | Direct Keycloak call - bypasses the `TokenProvider` cache |
| `GET` | `/cached-token` | Cached token - refreshed only when expired |
| `GET` | `/download-file/{session_id}` | Streams the session zip bundle |

It depends on FastAPI/uvicorn, which are **not** part of the runtime
client. Install the optional `integration-test` extra and run it:

```bash
pip install -e .[integration-test]
python examples/integration_test.py
```

The host binds to `http://localhost:7021` (matching the .NET sample) and
honours `UVICORN_HOST`, `UVICORN_PORT`, `UVICORN_SSL_CERTFILE` and
`UVICORN_SSL_KEYFILE` for HTTPS. Configuration is loaded from
environment / `.env` exactly like the quickstart script.

The companion VS Code REST Client scenarios live in
[`examples/ScanUpload.Api.Client.Test.http`](examples/ScanUpload.Api.Client.Test.http)
- open it with the REST Client extension and pick any request to send.
Equivalent `curl` invocations:

```bash
curl -k https://localhost:7021/health
curl -k https://localhost:7021/token | jq
curl -k https://localhost:7021/cached-token | jq
curl -k -OJ https://localhost:7021/download-file/<your session id>
```

## Running tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=scan_upload_api_client --cov-report=html
```

## Building the package

```bash
pip install build
python -m build
```

This creates both wheel and source distributions in `dist/`.

## Installing locally

```bash
pip install dist/scan_upload_api_client-1.0.0-py3-none-any.whl
```

## Publishing to PyPI

```bash
pip install twine
python -m twine upload dist/*
```

## Type checking (optional)

```bash
pip install mypy
mypy src/scan_upload_api_client
```

## Formatting (optional)

```bash
pip install ruff
ruff format src/ tests/ examples/
ruff check src/ tests/ examples/
```
