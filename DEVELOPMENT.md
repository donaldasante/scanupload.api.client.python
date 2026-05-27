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

To run FastAPI/ASGI examples, install ASGI extras:

```bash
pip install -e .[asgi]
```

The example scripts in `examples/` load values from `.env` first, then fall back
to environment variables using this precedence:

1. `SCANUPLOAD_DOTENV_PATH` (if set)
2. `.env` in the current working directory
3. `.env` in the repository root
4. Terminal environment variables

## Run FastAPI Example

```bash
python examples/fastapi_example.py
```

Default endpoint: `http://localhost:7021`

To run with HTTPS on `https://localhost:7021`, provide both SSL files in `.env`:

```ini
UVICORN_SSL_CERTFILE=C:/path/to/localhost.pem
UVICORN_SSL_KEYFILE=C:/path/to/localhost-key.pem
```

## Run Starlette Example

```bash
python examples/starlette_example.py
```

Default endpoint: `http://localhost:7021`

To run with HTTPS on `https://localhost:7021`, provide both SSL files in `.env`:

```ini
UVICORN_SSL_CERTFILE=C:/path/to/localhost.pem
UVICORN_SSL_KEYFILE=C:/path/to/localhost-key.pem
```

### Generate Local Certs (Windows)

```powershell
mkcert -install
mkcert -cert-file localhost.pem -key-file localhost-key.pem localhost 127.0.0.1 ::1
```

## Running Tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=scan_upload_api_client --cov-report=html
```

## Building the Package

```bash
pip install build
python -m build
```

This creates both wheel and source distributions in `dist/`.

## Installing Locally

```bash
pip install dist/scan_upload_api_client-0.1.0-py3-none-any.whl
```

## Publishing to PyPI

```bash
pip install twine
python -m twine upload dist/*
```

## Type Checking (Optional)

```bash
pip install mypy
mypy src/scan_upload_api_client
```

## Formatting (Optional)

```bash
pip install ruff
ruff format src/ tests/
ruff check src/ tests/
```
