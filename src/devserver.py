# Development entry point — runs the backend alone, without the pywebview window.
#
# The desktop app passes the auth token to the frontend in-process (main.py injects
# it as window.NCONOTES_TOKEN). The Vite dev server is a separate process on a
# separate port, so it has no such channel. This module bridges that gap: it writes
# the randomly chosen port and token to an owner-readable runtime file that the Vite
# proxy reads on every request.
#
# Port and token are generated exactly as main.py generates them — nothing is fixed
# or predictable. The runtime file exists only while this process is alive; the
# packaged desktop path (main.py) never writes it at all.
#
# Usage:  python src/devserver.py   (then, separately, cd src/frontend && npm run dev)

import atexit
import json
import os
import signal
import sys
from pathlib import Path

from backend.server import run
from main import find_free_port, generate_token

RUNTIME_FILE = Path(__file__).parent / "frontend" / ".nconotes-dev.json"


def _write_runtime_file(port: int, token: str) -> None:
    """Write {port, token} with owner-only permissions."""
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    # os.open with mode 0o600 so the token is never briefly world-readable.
    fd = os.open(RUNTIME_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"port": port, "token": token}, handle)


def _remove_runtime_file() -> None:
    try:
        RUNTIME_FILE.unlink()
    except FileNotFoundError:
        pass


def main() -> None:
    port = find_free_port()
    token = generate_token()

    _write_runtime_file(port, token)
    atexit.register(_remove_runtime_file)
    # atexit does not run on SIGTERM; convert it to a normal interpreter exit.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    print(f"NCONotes dev backend on http://127.0.0.1:{port}")
    print(f"Runtime file: {RUNTIME_FILE}")
    print("Start the frontend with: cd src/frontend && npm run dev")

    run(port, token)


if __name__ == "__main__":
    main()
