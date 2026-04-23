from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import typer
import uvicorn

from coco_flow.config import Settings, load_settings

from .paths import gateway_log_path, gateway_pid_path, gateway_state_path

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 4319


def serve_gateway(
    host: str = DEFAULT_GATEWAY_HOST,
    port: int = DEFAULT_GATEWAY_PORT,
) -> None:
    uvicorn.run(
        "coco_flow.gateway.api:create_gateway_app",
        host=host,
        port=port,
        factory=True,
    )


def start_gateway_in_background(
    *,
    host: str = DEFAULT_GATEWAY_HOST,
    port: int = DEFAULT_GATEWAY_PORT,
    settings: Settings | None = None,
) -> None:
    cfg = settings or load_settings()
    info = gateway_status(cfg)
    if info["running"]:
        typer.echo(f"coco-flow gateway already running (pid={info['pid']})")
        typer.echo(f"url: {info['url']}")
        typer.echo(f"log: {info['log_file']}")
        return

    cfg.config_root.mkdir(parents=True, exist_ok=True)
    log_path = gateway_log_path(cfg.config_root)
    pid_path = gateway_pid_path(cfg.config_root)
    state_path = gateway_state_path(cfg.config_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "coco_flow.gateway.api:create_gateway_app",
        "--host",
        host,
        "--port",
        str(port),
        "--factory",
    ]

    env = os.environ.copy()
    env["COCO_FLOW_CONFIG_DIR"] = str(cfg.config_root)
    env["COCO_FLOW_TASK_ROOT"] = str(cfg.task_root)
    env["COCO_FLOW_COCO_BIN"] = cfg.coco_bin
    env["COCO_FLOW_NATIVE_QUERY_TIMEOUT"] = cfg.native_query_timeout
    env["COCO_FLOW_NATIVE_CODE_TIMEOUT"] = str(cfg.native_code_timeout)
    env["COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS"] = str(cfg.acp_idle_timeout_seconds)
    env["COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS"] = str(cfg.daemon_idle_timeout_seconds)

    with log_path.open("a", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        pid_path.write_text(f"{proc.pid}\n", encoding="utf-8")
        _write_gateway_state(
            state_path,
            {
                "pid": proc.pid,
                "host": host,
                "port": int(port),
                "started_at": _now_iso(),
            },
        )

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            code = proc.poll()
            if code is not None:
                _cleanup_gateway_files(cfg, proc.pid)
                typer.echo(f"coco-flow gateway failed to start, see log: {log_path}", err=True)
                raise typer.Exit(code=code or 1)
            if _probe_gateway_health(host, port, timeout=0.2):
                typer.echo(f"coco-flow gateway started in background (pid={proc.pid})")
                typer.echo(f"url: http://{host}:{port}")
                typer.echo(f"log: {log_path}")
                typer.echo("stop: coco-flow gateway stop")
                return
            time.sleep(0.1)

    _cleanup_gateway_files(cfg, proc.pid)
    typer.echo(f"coco-flow gateway did not become healthy, see log: {log_path}", err=True)
    raise typer.Exit(code=1)


def gateway_status(settings: Settings | None = None) -> dict[str, object]:
    cfg = settings or load_settings()
    pid_path = gateway_pid_path(cfg.config_root)
    log_path = gateway_log_path(cfg.config_root)
    state = _read_gateway_state(gateway_state_path(cfg.config_root))
    host = str(state.get("host") or DEFAULT_GATEWAY_HOST)
    port = int(state.get("port") or DEFAULT_GATEWAY_PORT)
    pid = _read_pid_file(pid_path)
    running = False
    if pid is not None and _is_gateway_process(pid):
        running = True
    else:
        _cleanup_gateway_files(cfg, pid)
        pid = None
    return {
        "running": running,
        "healthy": _probe_gateway_health(host, port, timeout=0.2) if running else False,
        "pid": pid,
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}",
        "pid_file": str(pid_path),
        "log_file": str(log_path),
    }


def stop_gateway(settings: Settings | None = None, timeout_seconds: float = 5.0) -> None:
    cfg = settings or load_settings()
    pid_path = gateway_pid_path(cfg.config_root)
    pid = _read_pid_file(pid_path)
    if pid is None:
        return
    if not _is_gateway_process(pid):
        _cleanup_gateway_files(cfg, pid)
        return

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_gateway_process(pid):
            _cleanup_gateway_files(cfg, pid)
            return
        time.sleep(0.1)
    raise typer.Exit(code=1)


def _probe_gateway_health(host: str, port: int, timeout: float = 1.0) -> bool:
    url = f"http://{host}:{port}/healthz"
    try:
        with urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", 0) or 0
            payload = json.loads(response.read().decode("utf-8", "ignore"))
        return status == 200 and isinstance(payload, dict) and bool(payload.get("ok"))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


def _read_pid_file(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    raw = pid_path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_gateway_process(pid: int) -> bool:
    if pid <= 0:
        return False
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    command = result.stdout.strip()
    return "coco_flow.gateway.api:create_gateway_app" in command


def _read_gateway_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_gateway_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cleanup_gateway_files(settings: Settings, pid: int | None) -> None:
    pid_path = gateway_pid_path(settings.config_root)
    state_path = gateway_state_path(settings.config_root)
    if pid is not None and pid_path.exists():
        current = _read_pid_file(pid_path)
        if current == pid:
            pid_path.unlink(missing_ok=True)
    elif pid is None:
        pid_path.unlink(missing_ok=True)
    state_path.unlink(missing_ok=True)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()
