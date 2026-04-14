from __future__ import annotations

from pathlib import Path


def daemon_socket_path(config_root: Path) -> Path:
    return config_root / "daemon.sock"


def daemon_pid_path(config_root: Path) -> Path:
    return config_root / "daemon.pid"


def daemon_log_path(config_root: Path) -> Path:
    return config_root / "daemon.log"
