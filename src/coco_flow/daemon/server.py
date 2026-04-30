from __future__ import annotations

from pathlib import Path
import json
import os
import socket
import threading
import time

from coco_flow.clients.acp_client import (
    close_session_with_pool,
    new_session_with_pool,
    prompt_session_stream_with_pool,
    prompt_session_with_pool,
    run_prompt_stream_with_pool,
    run_prompt_with_pool,
)
from coco_flow.config import Settings, load_settings
from coco_flow.daemon.paths import daemon_log_path, daemon_pid_path, daemon_socket_path


class DaemonServer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.socket_path = daemon_socket_path(settings.config_root)
        self.pid_path = daemon_pid_path(settings.config_root)
        self.log_path = daemon_log_path(settings.config_root)
        self._listener: socket.socket | None = None
        self._shutdown = threading.Event()
        self._last_active = time.monotonic()

    def serve_forever(self) -> None:
        self.settings.config_root.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(str(self.socket_path))
        self._listener.listen()
        os.chmod(self.socket_path, 0o600)
        self.pid_path.write_text(str(os.getpid()))
        self._log(f"daemon started pid={os.getpid()} socket={self.socket_path}")

        threading.Thread(target=self._idle_watch, name="coco-flow-daemon-idle", daemon=True).start()

        try:
            while not self._shutdown.is_set():
                try:
                    conn, _ = self._listener.accept()
                except OSError:
                    if self._shutdown.is_set():
                        break
                    raise
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
        finally:
            self.close()

    def close(self) -> None:
        self._shutdown.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self.socket_path.exists():
            self.socket_path.unlink()
        if self.pid_path.exists():
            self.pid_path.unlink()
        self._log("daemon stopped")

    def _handle_conn(self, conn: socket.socket) -> None:
        with conn:
            raw = self._read_json(conn)
            if raw is None:
                return
            self._last_active = time.monotonic()
            request_type = str(raw.get("type") or "")

            if request_type == "ping":
                self._write_json(conn, {"ok": True, "pid": os.getpid()})
                return
            if request_type == "shutdown":
                self._write_json(conn, {"ok": True})
                self._shutdown.set()
                if self._listener is not None:
                    try:
                        self._listener.close()
                    except OSError:
                        pass
                return
            if request_type == "prompt":
                self._handle_prompt(conn, raw)
                return
            if request_type == "prompt_stream":
                self._handle_prompt_stream(conn, raw)
                return
            if request_type == "session_new":
                self._handle_session_new(conn, raw)
                return
            if request_type == "session_prompt":
                self._handle_session_prompt(conn, raw)
                return
            if request_type == "session_prompt_stream":
                self._handle_session_prompt_stream(conn, raw)
                return
            if request_type == "session_close":
                self._handle_session_close(conn, raw)
                return
            if request_type:
                self._write_json(conn, {"ok": False, "error": f"unknown request type: {request_type}"})
                return
            self._write_json(conn, {"ok": False, "error": "missing request type"})

    def _handle_prompt(self, conn: socket.socket, raw: dict[str, object]) -> None:
        try:
            content = run_prompt_with_pool(
                coco_bin=str(raw.get("coco_bin") or self.settings.coco_bin),
                cwd=str(raw.get("cwd") or os.getcwd()),
                mode=str(raw.get("mode") or "agent"),
                query_timeout=str(raw.get("query_timeout") or self.settings.native_query_timeout),
                prompt=str(raw.get("prompt") or ""),
                idle_timeout_seconds=float(raw.get("acp_idle_timeout_seconds") or self.settings.acp_idle_timeout_seconds),
                fresh_session=bool(raw.get("fresh_session")),
            )
            self._write_json(conn, {"ok": True, "content": content})
        except Exception as error:
            self._log(f"prompt_error: {error}")
            self._write_json(conn, {"ok": False, "error": str(error)})

    def _handle_prompt_stream(self, conn: socket.socket, raw: dict[str, object]) -> None:
        chunks: list[str] = []
        try:
            for chunk in run_prompt_stream_with_pool(
                coco_bin=str(raw.get("coco_bin") or self.settings.coco_bin),
                cwd=str(raw.get("cwd") or os.getcwd()),
                mode=str(raw.get("mode") or "agent"),
                query_timeout=str(raw.get("query_timeout") or self.settings.native_query_timeout),
                prompt=str(raw.get("prompt") or ""),
                idle_timeout_seconds=float(raw.get("acp_idle_timeout_seconds") or self.settings.acp_idle_timeout_seconds),
                fresh_session=bool(raw.get("fresh_session")),
            ):
                chunks.append(chunk)
                self._write_json(conn, {"type": "chunk", "content": chunk})
            self._write_json(conn, {"type": "done", "content": "".join(chunks).strip()})
        except Exception as error:
            self._log(f"prompt_stream_error: {error}")
            self._write_json(conn, {"type": "error", "error": str(error)})

    def _handle_session_new(self, conn: socket.socket, raw: dict[str, object]) -> None:
        try:
            handle = new_session_with_pool(
                coco_bin=str(raw.get("coco_bin") or self.settings.coco_bin),
                cwd=str(raw.get("cwd") or os.getcwd()),
                mode=str(raw.get("mode") or "agent"),
                query_timeout=str(raw.get("query_timeout") or self.settings.native_query_timeout),
                idle_timeout_seconds=float(raw.get("acp_idle_timeout_seconds") or self.settings.acp_idle_timeout_seconds),
                role=str(raw.get("role") or "agent"),
            )
            self._write_json(
                conn,
                {
                    "ok": True,
                    "handle": {
                        "handle_id": handle.handle_id,
                        "cwd": handle.cwd,
                        "mode": handle.mode,
                        "query_timeout": handle.query_timeout,
                        "role": handle.role,
                    },
                },
            )
        except Exception as error:
            self._log(f"session_new_error: {error}")
            self._write_json(conn, {"ok": False, "error": str(error)})

    def _handle_session_prompt(self, conn: socket.socket, raw: dict[str, object]) -> None:
        try:
            content = prompt_session_with_pool(
                handle_id=str(raw.get("handle_id") or ""),
                prompt=str(raw.get("prompt") or ""),
            )
            self._write_json(conn, {"ok": True, "content": content})
        except Exception as error:
            self._log(f"session_prompt_error: {error}")
            self._write_json(conn, {"ok": False, "error": str(error)})

    def _handle_session_prompt_stream(self, conn: socket.socket, raw: dict[str, object]) -> None:
        chunks: list[str] = []
        try:
            for chunk in prompt_session_stream_with_pool(
                handle_id=str(raw.get("handle_id") or ""),
                prompt=str(raw.get("prompt") or ""),
            ):
                chunks.append(chunk)
                self._write_json(conn, {"type": "chunk", "content": chunk})
            self._write_json(conn, {"type": "done", "content": "".join(chunks).strip()})
        except Exception as error:
            self._log(f"session_prompt_stream_error: {error}")
            self._write_json(conn, {"type": "error", "error": str(error)})

    def _handle_session_close(self, conn: socket.socket, raw: dict[str, object]) -> None:
        try:
            close_session_with_pool(handle_id=str(raw.get("handle_id") or ""))
            self._write_json(conn, {"ok": True})
        except Exception as error:
            self._log(f"session_close_error: {error}")
            self._write_json(conn, {"ok": False, "error": str(error)})

    def _idle_watch(self) -> None:
        while not self._shutdown.is_set():
            time.sleep(30)
            if time.monotonic() - self._last_active < self.settings.daemon_idle_timeout_seconds:
                continue
            self._log("daemon idle timeout reached")
            self._shutdown.set()
            if self._listener is not None:
                try:
                    self._listener.close()
                except OSError:
                    pass
            return

    def _read_json(self, conn: socket.socket) -> dict[str, object] | None:
        buffer = bytearray()
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            if b"\n" in chunk:
                break
        if not buffer:
            return None
        line = bytes(buffer).split(b"\n", 1)[0]
        return json.loads(line.decode("utf-8"))

    def _write_json(self, conn: socket.socket, payload: dict[str, object]) -> None:
        conn.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

    def _log(self, line: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(f"{timestamp} {line}\n")


def run_daemon_server(settings: Settings | None = None) -> None:
    DaemonServer(settings or load_settings()).serve_forever()


if __name__ == "__main__":
    run_daemon_server()
