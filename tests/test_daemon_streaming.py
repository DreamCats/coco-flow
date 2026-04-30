from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.daemon.client import stream_request
from coco_flow.daemon.paths import daemon_socket_path
from coco_flow.daemon.server import DaemonServer


class DaemonStreamingTest(unittest.TestCase):
    def test_stream_request_reads_ndjson_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = _settings(Path(temp))
            sock_path = daemon_socket_path(settings.config_root)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(sock_path))
            listener.listen(1)
            received: list[dict[str, object]] = []

            def serve_once() -> None:
                conn, _ = listener.accept()
                with conn:
                    raw = conn.recv(4096)
                    received.append(json.loads(raw.split(b"\n", 1)[0].decode("utf-8")))
                    conn.sendall(b'{"type":"chunk","content":"hel"}\n')
                    conn.sendall(b'{"type":"done","content":"hel"}\n')
                listener.close()

            thread = threading.Thread(target=serve_once)
            thread.start()
            events = list(stream_request(settings, {"type": "prompt_stream", "prompt": "x"}))
            thread.join(timeout=2)

        self.assertEqual(received, [{"type": "prompt_stream", "prompt": "x"}])
        self.assertEqual(
            events,
            [
                {"type": "chunk", "content": "hel"},
                {"type": "done", "content": "hel"},
            ],
        )

    def test_stream_request_rejects_empty_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            settings = _settings(Path(temp))
            sock_path = daemon_socket_path(settings.config_root)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(sock_path))
            listener.listen(1)

            def serve_once() -> None:
                conn, _ = listener.accept()
                conn.close()
                listener.close()

            thread = threading.Thread(target=serve_once)
            thread.start()
            with self.assertRaisesRegex(OSError, "without stream response"):
                list(stream_request(settings, {"type": "prompt_stream"}))
            thread.join(timeout=2)

    def test_prompt_stream_handler_writes_chunk_and_done_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = DaemonServer(_settings(Path(temp)))
            with patch("coco_flow.daemon.server.run_prompt_stream_with_pool", return_value=iter(["hel", "lo"])):
                events = _handle_request(
                    server,
                    {
                        "type": "prompt_stream",
                        "coco_bin": "coco",
                        "cwd": "/tmp/demo",
                        "mode": "agent",
                        "query_timeout": "90s",
                        "prompt": "prompt",
                        "acp_idle_timeout_seconds": 600,
                    },
                )

        self.assertEqual(
            events,
            [
                {"type": "chunk", "content": "hel"},
                {"type": "chunk", "content": "lo"},
                {"type": "done", "content": "hello"},
            ],
        )

    def test_session_prompt_stream_handler_writes_error_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = DaemonServer(_settings(Path(temp)))
            with patch("coco_flow.daemon.server.prompt_session_stream_with_pool", side_effect=ValueError("boom")):
                events = _handle_request(
                    server,
                    {
                        "type": "session_prompt_stream",
                        "handle_id": "handle-1",
                        "prompt": "prompt",
                    },
                )

        self.assertEqual(events, [{"type": "error", "error": "boom"}])


def _handle_request(server: DaemonServer, payload: dict[str, object]) -> list[dict[str, object]]:
    server_sock, client_sock = socket.socketpair()
    thread = threading.Thread(target=server._handle_conn, args=(server_sock,))
    thread.start()
    with client_sock:
        client_sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        events = _read_events(client_sock)
    thread.join(timeout=2)
    return events


def _read_events(sock: socket.socket) -> list[dict[str, object]]:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return [
        json.loads(line.decode("utf-8"))
        for line in bytes(data).splitlines()
        if line
    ]


def _settings(root: Path) -> Settings:
    return Settings(
        config_root=root,
        task_root=root / "tasks",
        refine_executor="native",
        plan_executor="native",
        code_executor="native",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="180s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600,
        daemon_idle_timeout_seconds=3600,
    )


if __name__ == "__main__":
    unittest.main()
