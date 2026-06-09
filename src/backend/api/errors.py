# Shared error response helpers for API routers.

from fastapi.responses import JSONResponse


def error_response(status: int, error: str, detail: str) -> JSONResponse:
    """Build a JSON error response in the standard {error, detail} format."""
    return JSONResponse({"error": error, "detail": detail}, status_code=status)
