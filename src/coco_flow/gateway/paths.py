from __future__ import annotations

from pathlib import Path


def gateway_pid_path(config_root: Path) -> Path:
    return config_root / "gateway.pid"


def gateway_log_path(config_root: Path) -> Path:
    return config_root / "gateway.log"


def gateway_state_path(config_root: Path) -> Path:
    return config_root / "gateway.json"
