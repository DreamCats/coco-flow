from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import typer
import uvicorn

from coco_flow.api import create_app
from coco_flow.config import load_settings
from coco_flow.daemon.paths import server_log_path, server_pid_path
from coco_flow.services.runtime.build_meta import build_meta_for_root

_WEB_BUILD_STAMP = ".coco-flow-build.json"


def run_background_server_entrypoint() -> None:
    pid_file_value = os.getenv("COCO_FLOW_SERVER_PID_FILE", "").strip()
    if pid_file_value:
        pid_path = Path(pid_file_value).expanduser()
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        atexit.register(_cleanup_server_pid_file, pid_path, os.getpid())
    from .app import app

    app()


def serve_api(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    reload: bool = typer.Option(False, help="Enable reload for local development."),
) -> None:
    uvicorn.run(
        "coco_flow.api:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


def serve_ui(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(4318, min=1, max=65535, help="Bind port."),
    web_dir: str = typer.Option("", help="Override the static web directory."),
    build_web: bool = typer.Option(True, "--build/--no-build", help="Build the web UI before serving."),
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    resolved_web_dir = Path(web_dir).expanduser().resolve() if web_dir else project_root / "web" / "dist"
    source_web_dir = project_root / "web"

    if build_web:
        ensure_web_build(source_web_dir, force=False)

    if not resolved_web_dir.is_dir():
        raise typer.BadParameter(f"web dir does not exist: {resolved_web_dir}")

    typer.echo("coco-flow ui serve")
    typer.echo(f"  host: {host}")
    typer.echo(f"  port: {port}")
    typer.echo(f"  web: {resolved_web_dir}")
    typer.echo(f"  local: http://127.0.0.1:{port}")
    typer.echo(f"  remote: http://<dev-machine-ip>:{port}")
    typer.echo("  tip: 远程开发机上运行时，优先在本地电脑建立 SSH 隧道")
    typer.echo(
        f"       ssh -fN -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 "
        f"-L {port}:127.0.0.1:{port} <user>@<dev-machine>"
    )
    typer.echo(f"       然后在本地浏览器打开 http://127.0.0.1:{port}")
    typer.echo(
        f"       关闭隧道可执行: pkill -f 'ssh .* -L {port}:127.0.0.1:{port} .*<user>@<dev-machine>'"
    )
    typer.echo("       如需让服务持续运行，可改用: coco-flow start --detach")
    uvicorn.run(
        create_app(static_dir=str(resolved_web_dir)),
        host=host,
        port=port,
    )


def ensure_web_build(web_root: Path, *, force: bool = False) -> None:
    if not web_root.is_dir():
        raise typer.BadParameter(f"web source directory not found: {web_root}")

    node_modules = web_root / "node_modules"
    if not node_modules.is_dir():
        install = subprocess.run(
            ["npm", "install"],
            cwd=web_root,
            check=False,
        )
        if install.returncode != 0:
            raise typer.Exit(code=install.returncode)

    if not force and not _web_build_is_stale(web_root):
        return

    build = subprocess.run(
        ["npm", "run", "build"],
        cwd=web_root,
        check=False,
    )
    if build.returncode != 0:
        raise typer.Exit(code=build.returncode)
    _write_web_build_stamp(web_root)


def start_server_in_background(
    *,
    host: str,
    port: int,
    web_dir: str,
    build_web: bool,
    api_only: bool,
    reload: bool,
) -> None:
    cfg = load_settings()
    info = server_status(cfg)
    if info["running"]:
        typer.echo(f"coco-flow server already running (pid={info['pid']})")
        typer.echo(f"log: {info['log_file']}")
        return

    cfg.config_root.mkdir(parents=True, exist_ok=True)
    log_path = server_log_path(cfg.config_root)
    pid_path = server_pid_path(cfg.config_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-c",
        "from coco_flow.cli import run_background_server_entrypoint; run_background_server_entrypoint()",
        "start",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if web_dir:
        command.extend(["--web-dir", web_dir])
    if not build_web:
        command.append("--no-build")
    if api_only:
        command.append("--api-only")
    if reload:
        command.append("--reload")

    env = os.environ.copy()
    env["COCO_FLOW_CONFIG_DIR"] = str(cfg.config_root)
    env["COCO_FLOW_TASK_ROOT"] = str(cfg.task_root)
    env["COCO_FLOW_COCO_BIN"] = cfg.coco_bin
    env["COCO_FLOW_NATIVE_QUERY_TIMEOUT"] = cfg.native_query_timeout
    env["COCO_FLOW_NATIVE_CODE_TIMEOUT"] = str(cfg.native_code_timeout)
    env["COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS"] = str(cfg.acp_idle_timeout_seconds)
    env["COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS"] = str(cfg.daemon_idle_timeout_seconds)
    env["COCO_FLOW_SERVER_PID_FILE"] = str(pid_path)

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

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            code = proc.poll()
            if code is not None:
                _cleanup_server_pid_file(pid_path, proc.pid)
                typer.echo(f"coco-flow server failed to start, see log: {log_path}", err=True)
                raise typer.Exit(code=code or 1)
            time.sleep(0.1)

    typer.echo(f"coco-flow server started in background (pid={proc.pid})")
    typer.echo(f"log: {log_path}")
    typer.echo("stop: coco-flow stop")


def server_status(settings=None) -> dict[str, object]:
    cfg = settings or load_settings()
    pid_path = server_pid_path(cfg.config_root)
    log_path = server_log_path(cfg.config_root)
    pid = _read_pid_file(pid_path)
    running = False
    if pid is not None and _is_server_process(pid):
        running = True
    else:
        _cleanup_server_pid_file(pid_path, pid)
        pid = None
    return {
        "running": running,
        "pid": pid,
        "pid_file": str(pid_path),
        "log_file": str(log_path),
    }


def stop_server(settings=None, timeout_seconds: float = 5.0) -> None:
    cfg = settings or load_settings()
    pid_path = server_pid_path(cfg.config_root)
    pid = _read_pid_file(pid_path)
    if pid is None:
        return
    if not _is_server_process(pid):
        _cleanup_server_pid_file(pid_path, pid)
        return

    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _is_server_process(pid):
            _cleanup_server_pid_file(pid_path, pid)
            return
        time.sleep(0.1)
    raise typer.Exit(code=1)


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


def _is_server_process(pid: int) -> bool:
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
    return "run_background_server_entrypoint" in command


def _cleanup_server_pid_file(pid_path: Path, pid: int | None) -> None:
    if pid is None or not pid_path.exists():
        return
    current = _read_pid_file(pid_path)
    if current == pid:
        pid_path.unlink(missing_ok=True)


def _web_build_is_stale(web_root: Path) -> bool:
    dist_dir = web_root / "dist"
    index_file = dist_dir / "index.html"
    stamp = _read_web_build_stamp(web_root)
    if not dist_dir.is_dir() or not index_file.is_file() or stamp is None:
        return True
    current_fingerprint = str(build_meta_for_root(web_root.parent).get("fingerprint") or "")
    stamp_fingerprint = str(stamp.get("fingerprint") or "")
    if not current_fingerprint or not stamp_fingerprint:
        return True
    return current_fingerprint != stamp_fingerprint


def _write_web_build_stamp(web_root: Path) -> None:
    dist_dir = web_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    payload = build_meta_for_root(web_root.parent)
    (dist_dir / _WEB_BUILD_STAMP).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_web_build_stamp(web_root: Path) -> dict[str, object] | None:
    stamp_path = web_root / "dist" / _WEB_BUILD_STAMP
    if not stamp_path.is_file():
        return None
    try:
        payload = json.loads(stamp_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
