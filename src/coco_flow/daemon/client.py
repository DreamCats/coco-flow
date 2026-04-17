from __future__ import annotations

from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time

from coco_flow.config import Settings, load_settings
from coco_flow.daemon.paths import daemon_log_path, daemon_pid_path, daemon_socket_path


def run_prompt_via_daemon(
    *,
    settings: Settings,
    coco_bin: str,
    cwd: str,
    mode: str,
    query_timeout: str,
    prompt: str,
    acp_idle_timeout_seconds: float,
    fresh_session: bool = False,
) -> str:
    ensure_daemon_running(settings)
    response = send_request(
        settings,
        {
            "type": "prompt",
            "coco_bin": coco_bin,
            "cwd": cwd,
            "mode": mode,
            "query_timeout": query_timeout,
            "prompt": prompt,
            "acp_idle_timeout_seconds": acp_idle_timeout_seconds,
            "fresh_session": fresh_session,
        },
    )
    if not response.get("ok"):
        raise ValueError(str(response.get("error") or "daemon prompt failed"))
    content = response.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("daemon prompt returned empty content")
    return content


def ensure_daemon_running(settings: Settings | None = None) -> None:
    cfg = settings or load_settings()
    try:
        ping(cfg)
        return
    except OSError:
        start_daemon(cfg)
        wait_for_daemon(cfg)


def ping(settings: Settings | None = None) -> dict[str, object]:
    cfg = settings or load_settings()
    return send_request(cfg, {"type": "ping"})


def shutdown(settings: Settings | None = None) -> None:
    cfg = settings or load_settings()
    try:
        send_request(cfg, {"type": "shutdown"})
    except OSError:
        return


def status(settings: Settings | None = None) -> dict[str, object]:
    cfg = settings or load_settings()
    running = False
    pid = None
    try:
        response = ping(cfg)
        running = bool(response.get("ok"))
        pid_value = response.get("pid")
        if isinstance(pid_value, int):
            pid = pid_value
    except OSError:
        running = False
    return {
        "running": running,
        "pid": pid,
        "socket": str(daemon_socket_path(cfg.config_root)),
        "pid_file": str(daemon_pid_path(cfg.config_root)),
        "log_file": str(daemon_log_path(cfg.config_root)),
    }


def start_daemon(settings: Settings | None = None) -> None:
    cfg = settings or load_settings()
    try:
        ping(cfg)
        return
    except OSError:
        pass
    cfg.config_root.mkdir(parents=True, exist_ok=True)
    log_path = daemon_log_path(cfg.config_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8")
    env = os.environ.copy()
    env["COCO_FLOW_CONFIG_DIR"] = str(cfg.config_root)
    env["COCO_FLOW_TASK_ROOT"] = str(cfg.task_root)
    env["COCO_FLOW_COCO_BIN"] = cfg.coco_bin
    env["COCO_FLOW_NATIVE_QUERY_TIMEOUT"] = cfg.native_query_timeout
    env["COCO_FLOW_NATIVE_CODE_TIMEOUT"] = cfg.native_code_timeout
    env["COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS"] = str(cfg.acp_idle_timeout_seconds)
    env["COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS"] = str(cfg.daemon_idle_timeout_seconds)
    subprocess.Popen(
        [sys.executable, "-m", "coco_flow.daemon.main"],
        cwd=str(Path.cwd()),
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )


def wait_for_daemon(settings: Settings | None = None, timeout_seconds: float = 10.0) -> None:
    cfg = settings or load_settings()
    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            ping(cfg)
            return
        except OSError as error:
            last_error = error
            time.sleep(0.1)
    raise OSError(f"daemon did not become ready: {last_error}")


def send_request(settings: Settings, payload: dict[str, object]) -> dict[str, object]:
    sock_path = daemon_socket_path(settings.config_root)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(sock_path))
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        data = _recv_line(client)
    return json.loads(data.decode("utf-8"))


def _recv_line(client: socket.socket) -> bytes:
    buffer = bytearray()
    while True:
        chunk = client.recv(4096)
        if not chunk:
            break
        buffer.extend(chunk)
        if b"\n" in chunk:
            break
    if not buffer:
        raise OSError("daemon closed connection without response")
    return bytes(buffer).split(b"\n", 1)[0]
