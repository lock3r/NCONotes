# Entry point for the NCONotes desktop application.
# Orchestrates the backend process and the pywebview desktop window.
#
# Two OS processes:
#   1. Backend  — FastAPI/uvicorn (spawned via multiprocessing)
#   2. Desktop  — pywebview window (runs in this process)
#
# The auth token is generated here and passed directly to both sides so neither
# has to read it from disk or the environment.

import multiprocessing
import secrets
import socket
import time
import urllib.error
import urllib.request


def find_free_port() -> int:
    """Ask the OS for an available port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _wait_for_backend(port: int, timeout: float = 30.0) -> None:
    """Poll /health until the backend responds or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"Backend did not become ready within {timeout:.0f}s")


def main() -> None:
    multiprocessing.set_start_method("spawn")

    port = find_free_port()
    token = generate_token()

    from backend.server import run as _run_backend

    backend = multiprocessing.Process(target=_run_backend, args=(port, token), daemon=True)
    backend.start()

    try:
        _wait_for_backend(port)

        import webview

        window = webview.create_window("NCONotes", f"http://127.0.0.1:{port}")
        # Inject the token each time a page finishes loading (covers refresh too).
        window.events.loaded += lambda: window.evaluate_js(
            f'window.NCONOTES_TOKEN = "{token}"'
        )
        webview.start()
    finally:
        backend.terminate()
        backend.join()


if __name__ == "__main__":
    main()
