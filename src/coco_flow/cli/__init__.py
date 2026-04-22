from __future__ import annotations

from .app import app
from .server import run_background_server_entrypoint, serve_ui, server_status, stop_server
from .project import installed_repo_root


def main() -> None:
    app()


__all__ = [
    "app",
    "installed_repo_root",
    "main",
    "run_background_server_entrypoint",
    "serve_ui",
    "server_status",
    "stop_server",
]
