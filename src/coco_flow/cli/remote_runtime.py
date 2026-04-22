from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import webbrowser

from coco_flow.config import Settings, load_settings
from coco_flow.services.runtime.build_meta import current_build_meta

LogHandler = Callable[[str], None]
_REMOTE_HEALTH_SCRIPT = """
import sys
import urllib.request

url = sys.argv[1]
ok = False

try:
    with urllib.request.urlopen(url, timeout=1.0) as response:
        status = getattr(response, "status", 0) or 0
        body = response.read().decode("utf-8", "ignore").lower()
        ok = status == 200 and "ok" in body
except Exception:
    ok = False

raise SystemExit(0 if ok else 1)
""".strip()
_REMOTE_META_SCRIPT = """
import json
import sys
import urllib.request

url = sys.argv[1]

try:
    with urllib.request.urlopen(url, timeout=1.0) as response:
        status = getattr(response, "status", 0) or 0
        if status != 200:
            raise SystemExit(1)
        payload = json.loads(response.read().decode("utf-8", "ignore"))
except Exception:
    raise SystemExit(1)

print(json.dumps(payload))
""".strip()


def connect_remote(
    host_or_ip: str,
    *,
    user: str | None = None,
    local_port: int | None = None,
    remote_port: int | None = None,
    restart: bool = False,
    reconnect_tunnel: bool = False,
    open_browser: bool = True,
    build_web: bool = True,
    settings: Settings | None = None,
    on_log: LogHandler | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    logger = on_log or (lambda _: None)
    raw_target = host_or_ip.strip()
    if not raw_target:
        raise ValueError("remote host is required")
    remote_config = _find_saved_remote(cfg, raw_target)
    target = str(remote_config.get("name") or raw_target) if remote_config else raw_target
    host = str(remote_config.get("host") or raw_target) if remote_config else raw_target
    resolved_user = user.strip() if isinstance(user, str) and user.strip() else str(remote_config.get("user") or "") if remote_config else ""
    resolved_local_port = int(local_port) if local_port is not None else int(remote_config.get("local_port") or 4318) if remote_config else 4318
    resolved_remote_port = int(remote_port) if remote_port is not None else int(remote_config.get("remote_port") or 4318) if remote_config else 4318

    records = _load_remote_records(cfg)
    matching_record = _find_matching_record(
        records,
        target=target,
        host=host,
        user=resolved_user,
        local_port=resolved_local_port,
        remote_port=resolved_remote_port,
    )
    local_health_url = _health_url(resolved_local_port)
    local_url = _remote_ui_url(_app_url(resolved_local_port), target=target, host=host)
    local_build = current_build_meta()
    initial_local_healthy = _probe_health(local_health_url)

    if not restart and not reconnect_tunnel and initial_local_healthy and matching_record is None:
        raise ValueError(
            f"local port {resolved_local_port} already serves a healthy endpoint, "
            "but it does not match the requested remote; use --local-port or disconnect the existing tunnel"
        )

    if restart:
        logger(f"remote_stop: {_build_ssh_target(host, resolved_user)}")
        _stop_remote_service(host, resolved_user)
        reconnect_tunnel = True

    remote_healthy = False if restart else _probe_remote_health(host, resolved_user, resolved_remote_port)
    remote_started = False
    remote_build: dict[str, Any] | None = None
    fingerprint_match: bool | None = None
    if remote_healthy:
        remote_build = _fetch_remote_meta(host, resolved_user, resolved_remote_port)
        fingerprint_match = _fingerprints_match(local_build, remote_build)
        logger(f"remote_reuse: {_build_ssh_target(host, resolved_user)}:{resolved_remote_port}")
        _log_fingerprint_status(
            logger,
            local_build=local_build,
            remote_build=remote_build,
            fingerprint_match=fingerprint_match,
            remote_started=False,
        )
    else:
        logger(f"remote_start: {_build_ssh_target(host, resolved_user)}:{resolved_remote_port}")
        _start_remote_service(host, resolved_user, remote_port=resolved_remote_port, build_web=build_web)
        remote_started = True
        if not _probe_remote_health(host, resolved_user, resolved_remote_port):
            raise ValueError(f"remote coco-flow did not become healthy on {host}:{resolved_remote_port}")
        remote_build = _fetch_remote_meta(host, resolved_user, resolved_remote_port)
        fingerprint_match = _fingerprints_match(local_build, remote_build)
        _log_fingerprint_status(
            logger,
            local_build=local_build,
            remote_build=remote_build,
            fingerprint_match=fingerprint_match,
            remote_started=True,
        )

    local_healthy = _probe_health(local_health_url)
    if reconnect_tunnel or not local_healthy:
        logger(f"tunnel_prepare: 127.0.0.1:{resolved_local_port} -> {_build_ssh_target(host, resolved_user)}:{resolved_remote_port}")
        records = _disconnect_records(
            records,
            [
                record
                for record in records
                if int(record.get("local_port") or 0) == resolved_local_port
            ],
        )
        _ensure_local_port_available(resolved_local_port)
        pid = _start_tunnel(host, resolved_user, local_port=resolved_local_port, remote_port=resolved_remote_port)
        logger(f"tunnel_start: pid={pid} local={resolved_local_port} remote={resolved_remote_port}")
        records = _upsert_remote_record(
            records,
            target=target,
            host=host,
            user=resolved_user,
            local_port=resolved_local_port,
            remote_port=resolved_remote_port,
            ssh_pid=pid,
        )
        _save_remote_records(cfg, records)
    else:
        logger(f"tunnel_reuse: {local_url}")
        if matching_record is not None:
            _touch_remote_record(records, matching_record, target=target, host=host, user=resolved_user)
            _save_remote_records(cfg, records)

    if not _probe_health(local_health_url):
        raise ValueError(f"local tunnel did not become healthy on {local_health_url}")

    if open_browser:
        logger(f"open_browser: {local_url}")
        webbrowser.open(local_url)

    return {
        "target": target,
        "host": host,
        "ssh_target": _build_ssh_target(host, resolved_user),
        "local_url": local_url,
        "local_build": local_build,
        "remote_build": remote_build,
        "fingerprint_match": fingerprint_match,
        "remote_started": remote_started,
        "tunnel_started": True if reconnect_tunnel or not local_healthy else False,
        "reused_local": initial_local_healthy and not reconnect_tunnel,
        "reused_remote": not remote_started,
    }


def disconnect_remote(
    host_or_ip: str = "",
    *,
    settings: Settings | None = None,
    on_log: LogHandler | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    logger = on_log or (lambda _: None)
    records = _load_remote_records(cfg)
    target = host_or_ip.strip()
    matched = [record for record in records if _record_matches_target(record, target)] if target else list(records)
    if not matched:
        raise ValueError(f"no managed remote tunnel found: {target or 'all'}")
    for record in matched:
        logger(f"tunnel_stop: {record.get('target') or record.get('host')} pid={record.get('ssh_pid')}")
    remaining = _disconnect_records(records, matched)
    _save_remote_records(cfg, remaining)
    return {
        "disconnected": len(matched),
        "targets": [str(record.get("target") or record.get("host") or "") for record in matched],
    }


def remote_status(
    host_or_ip: str = "",
    *,
    user: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    target = host_or_ip.strip()
    records = _load_remote_records(cfg)
    filtered = [record for record in records if _record_matches_target(record, target)] if target else records
    local_build = current_build_meta()
    connections: list[dict[str, Any]] = []
    for record in filtered:
        local_port = int(record.get("local_port") or 0)
        remote_port = int(record.get("remote_port") or 0)
        resolved_user = user.strip() if isinstance(user, str) and user.strip() else str(record.get("user") or "")
        current_target = str(record.get("target") or "")
        current_host = str(record.get("host") or current_target or "")
        local_health_url = _health_url(local_port)
        local_healthy = _probe_health(local_health_url)
        ssh_pid = int(record.get("ssh_pid") or 0)
        connection: dict[str, Any] = {
            "target": current_target,
            "host": current_host,
            "ssh_target": _build_ssh_target(current_host, resolved_user),
            "local_port": local_port,
            "remote_port": remote_port,
            "local_url": _app_url(local_port),
            "local_healthy": local_healthy,
            "tunnel_pid": ssh_pid,
            "tunnel_alive": _is_process_alive(ssh_pid),
            "created_at": str(record.get("created_at") or ""),
            "updated_at": str(record.get("updated_at") or ""),
        }
        if target:
            connection["remote_healthy"] = _probe_remote_health(current_host, resolved_user, remote_port)
            if connection["remote_healthy"]:
                connection["remote_build"] = _fetch_remote_meta(current_host, resolved_user, remote_port)
                connection["fingerprint_match"] = _fingerprints_match(local_build, connection.get("remote_build"))
        connections.append(connection)
    return {
        "connections": connections,
        "config_path": str(_remote_state_path(cfg)),
        "local_build": local_build,
        "remotes": list_remotes(settings=cfg)["remotes"],
    }


def add_remote(
    name: str,
    *,
    host: str,
    user: str = "",
    local_port: int = 4318,
    remote_port: int = 4318,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    normalized_name = name.strip()
    normalized_host = host.strip()
    normalized_user = user.strip()
    if not normalized_name:
        raise ValueError("remote name is required")
    if not normalized_host:
        raise ValueError("remote host is required")

    remotes = _load_saved_remotes(cfg)
    now = _now_iso()
    updated = False
    for remote in remotes:
        if str(remote.get("name") or "").strip() != normalized_name:
            continue
        remote.update(
            {
                "name": normalized_name,
                "host": normalized_host,
                "user": normalized_user,
                "local_port": int(local_port),
                "remote_port": int(remote_port),
                "updated_at": now,
            }
        )
        if not str(remote.get("created_at") or "").strip():
            remote["created_at"] = now
        updated = True
        break
    if not updated:
        remotes.append(
            {
                "name": normalized_name,
                "host": normalized_host,
                "user": normalized_user,
                "local_port": int(local_port),
                "remote_port": int(remote_port),
                "created_at": now,
                "updated_at": now,
            }
        )
    _save_saved_remotes(cfg, remotes)
    return {
        "name": normalized_name,
        "host": normalized_host,
        "user": normalized_user,
        "local_port": int(local_port),
        "remote_port": int(remote_port),
        "updated": updated,
    }


def list_remotes(*, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or load_settings()
    remotes = _load_saved_remotes(cfg)
    remotes.sort(key=lambda item: str(item.get("name") or ""))
    return {
        "remotes": remotes,
        "config_path": str(_saved_remotes_path(cfg)),
    }


def remove_remote(name: str, *, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or load_settings()
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("remote name is required")
    remotes = _load_saved_remotes(cfg)
    remaining = [remote for remote in remotes if str(remote.get("name") or "").strip() != normalized_name]
    if len(remaining) == len(remotes):
        raise ValueError(f"saved remote not found: {normalized_name}")
    _save_saved_remotes(cfg, remaining)
    return {"removed": normalized_name}


def _health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/healthz"


def _meta_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/api/meta"


def _app_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _remote_ui_url(base_url: str, *, target: str, host: str) -> str:
    query = urlencode(
        {
            "coco_flow_context": "remote",
            "remote_name": target,
            "remote_host": host,
        }
    )
    return f"{base_url}?{query}"


def _probe_health(url: str, timeout: float = 1.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", "ignore").lower()
            status = getattr(response, "status", 0) or 0
        return status == 200 and "ok" in body
    except (OSError, URLError, ValueError):
        return False


def _probe_remote_health(target: str, user: str, remote_port: int) -> bool:
    url = _health_url(remote_port)
    command = f"python3 -c {shlex.quote(_REMOTE_HEALTH_SCRIPT)} {shlex.quote(url)}"
    result = _run_ssh_command(target, user, command)
    return result.returncode == 0


def _fetch_remote_meta(target: str, user: str, remote_port: int) -> dict[str, Any] | None:
    url = _meta_url(remote_port)
    command = f"python3 -c {shlex.quote(_REMOTE_META_SCRIPT)} {shlex.quote(url)}"
    result = _run_ssh_command(target, user, command)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _start_remote_service(target: str, user: str, *, remote_port: int, build_web: bool) -> None:
    command = [
        "coco-flow",
        "start",
        "--detach",
        "--host",
        "127.0.0.1",
        "--port",
        str(remote_port),
    ]
    if not build_web:
        command.append("--no-build")
    result = _run_ssh_command(target, user, _shell_join(command))
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "failed to start remote coco-flow")


def _stop_remote_service(target: str, user: str) -> None:
    result = _run_ssh_command(target, user, "coco-flow stop")
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "failed to stop remote coco-flow")


def _start_tunnel(target: str, user: str, *, local_port: int, remote_port: int) -> int:
    ssh_target = _build_ssh_target(target, user)
    args = [
        "ssh",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=60",
        "-L",
        f"{local_port}:127.0.0.1:{remote_port}",
        ssh_target,
    ]
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            raise ValueError("failed to establish local SSH tunnel")
        if _probe_health(_health_url(local_port), timeout=0.2):
            return int(proc.pid)
        time.sleep(0.1)
    if proc.poll() is not None:
        raise ValueError("failed to establish local SSH tunnel")
    return int(proc.pid)


def _run_ssh_command(target: str, user: str, command: str) -> subprocess.CompletedProcess[str]:
    ssh_target = _build_ssh_target(target, user)
    return subprocess.run(
        ["ssh", ssh_target, f"sh -lc {shlex.quote(command)}"],
        check=False,
        capture_output=True,
        text=True,
    )


def _ensure_local_port_available(port: int) -> None:
    if _has_local_listener(port):
        raise ValueError(f"local port {port} is already in use")
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError as error:
        raise ValueError(f"local port {port} is already in use") from error
    finally:
        probe.close()


def _has_local_listener(port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.2)
    try:
        return probe.connect_ex(("127.0.0.1", port)) == 0
    finally:
        probe.close()


def _build_ssh_target(target: str, user: str) -> str:
    return f"{user.strip()}@{target}" if user.strip() else target


def _fingerprints_match(local_build: dict[str, Any], remote_build: dict[str, Any] | None) -> bool | None:
    if not remote_build:
        return None
    local_fingerprint = str(local_build.get("fingerprint") or "").strip()
    remote_fingerprint = str(remote_build.get("fingerprint") or "").strip()
    if not local_fingerprint or not remote_fingerprint:
        return None
    return local_fingerprint == remote_fingerprint


def _log_fingerprint_status(
    logger: LogHandler,
    *,
    local_build: dict[str, Any],
    remote_build: dict[str, Any] | None,
    fingerprint_match: bool | None,
    remote_started: bool,
) -> None:
    local_fingerprint = str(local_build.get("fingerprint") or "")
    if remote_build is None:
        logger("remote_meta_unavailable")
        return
    remote_fingerprint = str(remote_build.get("fingerprint") or "")
    if fingerprint_match is None:
        logger(f"remote_meta_unavailable: local={local_fingerprint} remote={remote_fingerprint or 'unknown'}")
        return
    if fingerprint_match:
        logger(f"remote_version_ok: local={local_fingerprint} remote={remote_fingerprint}")
        return
    logger(f"remote_version_mismatch: local={local_fingerprint} remote={remote_fingerprint}")
    if remote_started:
        logger("remote_version_action: remote service restarted, but the remote machine is still running a different coco-flow build")
        return
    logger("remote_version_action: rerun with --restart after the remote machine has been updated")


def _shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _remote_state_path(settings: Settings) -> Path:
    return settings.config_root / "remote" / "connections.json"


def _saved_remotes_path(settings: Settings) -> Path:
    return settings.config_root / "remote" / "remotes.json"


def _load_remote_records(settings: Settings) -> list[dict[str, Any]]:
    path = _remote_state_path(settings)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("connections")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _save_remote_records(settings: Settings, records: list[dict[str, Any]]) -> None:
    path = _remote_state_path(settings)
    if not records:
        path.unlink(missing_ok=True)
        if path.parent.exists():
            try:
                path.parent.rmdir()
            except OSError:
                pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"connections": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_saved_remotes(settings: Settings) -> list[dict[str, Any]]:
    path = _saved_remotes_path(settings)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("remotes")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _save_saved_remotes(settings: Settings, remotes: list[dict[str, Any]]) -> None:
    path = _saved_remotes_path(settings)
    if not remotes:
        path.unlink(missing_ok=True)
        _cleanup_remote_dir_if_empty(path.parent)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"remotes": remotes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _find_matching_record(
    records: list[dict[str, Any]],
    *,
    target: str,
    host: str,
    user: str,
    local_port: int,
    remote_port: int,
) -> dict[str, Any] | None:
    for record in records:
        if not _record_matches_request(record, target, host):
            continue
        record_user = str(record.get("user") or "").strip()
        if user.strip() and user.strip() != record_user:
            continue
        if int(record.get("local_port") or 0) != local_port:
            continue
        if int(record.get("remote_port") or 0) != remote_port:
            continue
        return record
    return None


def _record_matches_target(record: dict[str, Any], target: str) -> bool:
    if not target:
        return True
    normalized = target.strip()
    return normalized in {
        str(record.get("target") or "").strip(),
        str(record.get("host") or "").strip(),
    }


def _record_matches_request(record: dict[str, Any], target: str, host: str) -> bool:
    normalized_target = target.strip()
    normalized_host = host.strip()
    return normalized_target in {
        str(record.get("target") or "").strip(),
        str(record.get("host") or "").strip(),
    } or normalized_host in {
        str(record.get("target") or "").strip(),
        str(record.get("host") or "").strip(),
    }


def _find_saved_remote(settings: Settings, target: str) -> dict[str, Any] | None:
    normalized = target.strip()
    if not normalized:
        return None
    for remote in _load_saved_remotes(settings):
        if normalized in {
            str(remote.get("name") or "").strip(),
            str(remote.get("host") or "").strip(),
        }:
            return remote
    return None


def _upsert_remote_record(
    records: list[dict[str, Any]],
    *,
    target: str,
    host: str,
    user: str,
    local_port: int,
    remote_port: int,
    ssh_pid: int,
) -> list[dict[str, Any]]:
    next_records = [record for record in records if int(record.get("local_port") or 0) != local_port]
    now = _now_iso()
    next_records.append(
        {
            "target": target,
            "host": host,
            "user": user.strip(),
            "local_port": local_port,
            "remote_port": remote_port,
            "ssh_pid": ssh_pid,
            "created_at": now,
            "updated_at": now,
        }
    )
    return next_records


def _touch_remote_record(
    records: list[dict[str, Any]],
    record: dict[str, Any],
    *,
    target: str,
    host: str,
    user: str,
) -> None:
    record["target"] = target
    record["host"] = host
    if user.strip():
        record["user"] = user.strip()
    record["updated_at"] = _now_iso()


def _disconnect_records(
    records: list[dict[str, Any]],
    matched: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched_ids = {id(record) for record in matched}
    for record in matched:
        pid = int(record.get("ssh_pid") or 0)
        if pid > 0:
            _terminate_process(pid)
    return [record for record in records if id(record) not in matched_ids]


def _cleanup_remote_dir_if_empty(path: Path) -> None:
    if not path.exists():
        return
    try:
        next(path.iterdir())
    except StopIteration:
        path.rmdir()
    except OSError:
        return


def _terminate_process(pid: int) -> None:
    if not _is_process_alive(pid):
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            return
        time.sleep(0.1)
    if _is_process_alive(pid):
        os.kill(pid, signal.SIGKILL)


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()
