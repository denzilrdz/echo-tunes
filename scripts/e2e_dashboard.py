"""The real dashboard app with in-memory data, for the web end-to-end test (web/e2e/).

No YouTube, Amazon or Echo: browsing answers 404 and the UI must cope. It serves the committed
build with the real CSP, sign-in page and session cookies.

    uv run python scripts/e2e_dashboard.py 4174
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import uvicorn

from echo_tunes.dashboard import DashboardDeps, create_dashboard
from echo_tunes.history import History
from echo_tunes.player.store import StateStore

PASSWORD = "e2e-password"  # noqa: S105 - a throwaway test password


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4174
    with tempfile.TemporaryDirectory() as tmp:
        deps = DashboardDeps(
            store=StateStore(Path(tmp) / "players.sqlite3"),
            history=History(":memory:", 15),
            signed_in=lambda: False,
            password=PASSWORD,
            public_origin="https://music.example.com",
        )
        uvicorn.run(create_dashboard(deps), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
