from __future__ import annotations

from dataclasses import dataclass
from json import JSONDecodeError, JSONDecoder
import json
import os
import queue
import re
import subprocess
import threading
import time
import uuid

from .base import CocoClient
from coco_flow.config import Settings, load_settings
from coco_flow.daemon.client import (
    close_session_via_daemon,
    new_session_via_daemon,
    prompt_session_via_daemon,
    run_prompt_via_daemon,
)

_DURATION_PART = re.compile(r"(\d+)(ms|s|m|h)")


@dataclass(frozen=True)
class _ACPMode:
    name: str
    yolo: bool = True


AGENT_MODE = _ACPMode(name="agent")


@dataclass(frozen=True)
class _SessionKey:
    coco_bin: str
    cwd: str
    mode: _ACPMode
    query_timeout: str


@dataclass(frozen=True)
class AgentSessionHandle:
    handle_id: str
    cwd: str
    mode: str
    query_timeout: str
    role: str


@dataclass(frozen=True)
class _ExplicitSession:
    key: _SessionKey
    session_id: str
    role: str
    created_at: float


@dataclass
class _ACPResponse:
    payload: dict[str, object]

    @property
    def id(self) -> int | None:
        value = self.payload.get("id")
        return value if isinstance(value, int) else None

    @property
    def method(self) -> str:
        value = self.payload.get("method")
        return value if isinstance(value, str) else ""

    @property
    def result(self) -> object:
        return self.payload.get("result")

    @property
    def error(self) -> object:
        return self.payload.get("error")


class CocoACPClient(CocoClient):
    def __init__(
        self,
        coco_bin: str,
        idle_timeout_seconds: float = 600.0,
        settings: Settings | None = None,
    ) -> None:
        self.coco_bin = coco_bin
        self.idle_timeout_seconds = idle_timeout_seconds
        self.settings = settings or load_settings()

    def run_agent(
        self,
        prompt: str,
        query_timeout: str,
        cwd: str,
        *,
        fresh_session: bool = False,
    ) -> str:
        return run_prompt_via_daemon(
            settings=self.settings,
            coco_bin=self.coco_bin,
            cwd=os.path.realpath(cwd),
            mode=AGENT_MODE.name,
            query_timeout=query_timeout,
            prompt=prompt,
            acp_idle_timeout_seconds=self.idle_timeout_seconds,
            fresh_session=fresh_session,
        )

    def new_agent_session(
        self,
        *,
        query_timeout: str,
        cwd: str,
        role: str,
    ) -> AgentSessionHandle:
        payload = new_session_via_daemon(
            settings=self.settings,
            coco_bin=self.coco_bin,
            cwd=os.path.realpath(cwd),
            mode=AGENT_MODE.name,
            query_timeout=query_timeout,
            acp_idle_timeout_seconds=self.idle_timeout_seconds,
            role=role,
        )
        return _agent_session_handle_from_payload(payload)

    def prompt_agent_session(self, handle: AgentSessionHandle, prompt: str) -> str:
        return prompt_session_via_daemon(
            settings=self.settings,
            handle_id=handle.handle_id,
            prompt=prompt,
        )

    def close_agent_session(self, handle: AgentSessionHandle) -> None:
        close_session_via_daemon(
            settings=self.settings,
            handle_id=handle.handle_id,
        )


class _ACPSessionPool:
    def __init__(self) -> None:
        self._sessions: dict[_SessionKey, _PooledSession] = {}
        self._explicit_sessions: dict[str, _ExplicitSession] = {}
        self._lock = threading.Lock()
        self._reaper_started = False

    def run_prompt(
        self,
        coco_bin: str,
        cwd: str,
        mode: _ACPMode,
        query_timeout: str,
        prompt: str,
        idle_timeout_seconds: float,
        fresh_session: bool = False,
    ) -> str:
        self._ensure_reaper_started()
        key = _SessionKey(coco_bin=coco_bin, cwd=cwd, mode=mode, query_timeout=query_timeout)
        with self._lock:
            session = self._get_or_create_session_locked(key, coco_bin, idle_timeout_seconds)
        return session.prompt(prompt, fresh_session=fresh_session)

    def new_session(
        self,
        coco_bin: str,
        cwd: str,
        mode: _ACPMode,
        query_timeout: str,
        idle_timeout_seconds: float,
        role: str,
    ) -> AgentSessionHandle:
        self._ensure_reaper_started()
        key = _SessionKey(coco_bin=coco_bin, cwd=cwd, mode=mode, query_timeout=query_timeout)
        with self._lock:
            session = self._get_or_create_session_locked(key, coco_bin, idle_timeout_seconds)
        session_id = session.new_explicit_session()
        handle_id = uuid.uuid4().hex
        explicit_session = _ExplicitSession(
            key=key,
            session_id=session_id,
            role=role,
            created_at=time.monotonic(),
        )
        with self._lock:
            self._explicit_sessions[handle_id] = explicit_session
        return AgentSessionHandle(
            handle_id=handle_id,
            cwd=cwd,
            mode=mode.name,
            query_timeout=query_timeout,
            role=role,
        )

    def prompt_session(self, handle_id: str, prompt: str) -> str:
        with self._lock:
            explicit_session = self._explicit_sessions.get(handle_id)
            if explicit_session is None:
                raise ValueError(f"unknown acp session handle: {handle_id}")
            session = self._sessions.get(explicit_session.key)
            if session is None:
                raise ValueError(f"acp session handle is no longer active: {handle_id}")
        return session.prompt_explicit_session(explicit_session.session_id, prompt)

    def close_session(self, handle_id: str) -> None:
        with self._lock:
            self._explicit_sessions.pop(handle_id, None)

    def reap_idle_sessions(self) -> None:
        while True:
            time.sleep(30)
            now = time.monotonic()
            with self._lock:
                stale_keys = [
                    key for key, session in self._sessions.items()
                    if session.should_close(now)
                ]
                stale_sessions = [self._sessions.pop(key) for key in stale_keys]
                stale_key_set = set(stale_keys)
                if stale_key_set:
                    self._explicit_sessions = {
                        handle_id: explicit_session
                        for handle_id, explicit_session in self._explicit_sessions.items()
                        if explicit_session.key not in stale_key_set
                    }
            for session in stale_sessions:
                session.close()

    def _ensure_reaper_started(self) -> None:
        with self._lock:
            if self._reaper_started:
                return
            threading.Thread(target=self.reap_idle_sessions, name="coco-flow-acp-reaper", daemon=True).start()
            self._reaper_started = True

    def _get_or_create_session_locked(
        self,
        key: _SessionKey,
        coco_bin: str,
        idle_timeout_seconds: float,
    ) -> "_PooledSession":
        session = self._sessions.get(key)
        if session is None:
            session = _PooledSession(
                key=key,
                coco_bin=coco_bin,
                idle_timeout_seconds=idle_timeout_seconds,
            )
            self._sessions[key] = session
        return session


class _PooledSession:
    def __init__(
        self,
        key: _SessionKey,
        coco_bin: str,
        idle_timeout_seconds: float,
    ) -> None:
        self.key = key
        self.coco_bin = coco_bin
        self.idle_timeout_seconds = idle_timeout_seconds
        self._process: _ACPProcess | None = None
        self._session_id = ""
        self._lock = threading.Lock()
        self._last_used = time.monotonic()
        self._busy = False

    def prompt(self, prompt: str, *, fresh_session: bool = False) -> str:
        with self._lock:
            self._busy = True
            self._ensure_running()
            assert self._process is not None
            session_id = self._new_session_id() if fresh_session else self._session_id
            try:
                result = self._process.prompt(session_id, prompt)
            except ValueError:
                self._restart()
                assert self._process is not None
                session_id = self._new_session_id() if fresh_session else self._session_id
                result = self._process.prompt(session_id, prompt)
            finally:
                self._last_used = time.monotonic()
                self._busy = False
            return result

    def new_explicit_session(self) -> str:
        with self._lock:
            self._ensure_running()
            self._last_used = time.monotonic()
            return self._new_session_id()

    def prompt_explicit_session(self, session_id: str, prompt: str) -> str:
        with self._lock:
            self._busy = True
            if self._process is None or not self._process.is_running():
                self._busy = False
                raise ValueError("explicit acp session is no longer running")
            try:
                result = self._process.prompt(session_id, prompt)
            finally:
                self._last_used = time.monotonic()
                self._busy = False
            return result

    def should_close(self, now: float) -> bool:
        return not self._busy and now - self._last_used >= self.idle_timeout_seconds

    def close(self) -> None:
        with self._lock:
            if self._process is not None:
                self._process.close()
                self._process = None
                self._session_id = ""

    def _ensure_running(self) -> None:
        if self._process is not None and self._process.is_running():
            return
        self._restart()

    def _new_session_id(self) -> str:
        assert self._process is not None
        return self._process.new_session(self.key.cwd)

    def _restart(self) -> None:
        if self._process is not None:
            self._process.close()
        self._process = _ACPProcess(
            cmd=_build_acp_command(self.coco_bin, self.key.mode, self.key.query_timeout),
            cwd=self.key.cwd,
            timeout_seconds=_parse_duration_seconds(self.key.query_timeout),
        )
        self._process.start()
        self._process.initialize()
        self._session_id = self._process.new_session(self.key.cwd)
        self._last_used = time.monotonic()


class _ACPProcess:
    def __init__(self, cmd: list[str], cwd: str, timeout_seconds: float) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.timeout_seconds = max(timeout_seconds, 1.0)
        self.process: subprocess.Popen[bytes] | None = None
        self._messages: queue.Queue[_ACPResponse] = queue.Queue()
        self._stderr_chunks: list[str] = []
        self._next_id = 0
        self._reader_started = False

    def start(self) -> None:
        try:
            self.process = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
            )
        except FileNotFoundError as error:
            raise ValueError(f"acp coco executable not found: {self.cmd[0]}") from error

        assert self.process.stdout is not None
        assert self.process.stderr is not None

        if not self._reader_started:
            threading.Thread(target=self._read_stdout, name="coco-flow-acp-stdout", daemon=True).start()
            threading.Thread(target=self._read_stderr, name="coco-flow-acp-stderr", daemon=True).start()
            self._reader_started = True

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def initialize(self) -> None:
        response = self._request(
            "initialize",
            {
                "protocolVersion": 1,
                "capabilities": {},
                "clientInfo": {"name": "coco-flow", "version": "0.1.0"},
            },
        )
        self._raise_rpc_error(response, "initialize")

    def new_session(self, cwd: str) -> str:
        response = self._request(
            "session/new",
            {
                "cwd": cwd,
                "mcpServers": [],
            },
        )
        self._raise_rpc_error(response, "session/new")
        result = response.result
        if not isinstance(result, dict):
            raise ValueError("acp session/new missing result")
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("acp session/new missing sessionId")
        return session_id

    def prompt(self, session_id: str, prompt: str) -> str:
        request_id = self._send(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
        )

        chunks: list[str] = []
        deadline = time.monotonic() + self.timeout_seconds + 15.0

        while True:
            remaining = max(deadline - time.monotonic(), 0.1)
            response = self._next_message(timeout=remaining)
            if response is None:
                raise ValueError(self._build_timeout_error("session/prompt"))

            if response.id == request_id:
                self._raise_rpc_error(response, "session/prompt")
                break

            if response.method != "session/update":
                continue

            params = response.payload.get("params")
            if not isinstance(params, dict):
                continue
            update = params.get("update")
            if not isinstance(update, dict):
                continue
            session_update = update.get("sessionUpdate")
            if session_update != "agent_message_chunk":
                continue
            content = update.get("content")
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text:
                chunks.append(text)

        content = "".join(chunks).strip()
        if not content:
            raise ValueError("acp prompt returned empty content")
        return content

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.stdin is not None and not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None

    def _request(self, method: str, params: dict[str, object]) -> _ACPResponse:
        request_id = self._send(method, params)
        deadline = time.monotonic() + self.timeout_seconds + 10.0
        while True:
            remaining = max(deadline - time.monotonic(), 0.1)
            response = self._next_message(timeout=remaining)
            if response is None:
                raise ValueError(self._build_timeout_error(method))
            if response.id == request_id:
                return response

    def _send(self, method: str, params: dict[str, object]) -> int:
        if self.process is None or self.process.stdin is None:
            raise ValueError("acp process is not running")
        self._next_id += 1
        request_id = self._next_id
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        try:
            self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            self.process.stdin.flush()
        except OSError as error:
            raise ValueError(f"acp write failed: {error}") from error
        return request_id

    def _next_message(self, timeout: float) -> _ACPResponse | None:
        try:
            return self._messages.get(timeout=timeout)
        except queue.Empty:
            if not self.is_running():
                raise ValueError(self._build_timeout_error("process_exit"))
            return None

    def _read_stdout(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        decoder = JSONDecoder()
        buffer = ""
        while True:
            if self.process is None or self.process.stdout is None:
                return
            chunk = os.read(self.process.stdout.fileno(), 4096)
            if not chunk:
                return
            buffer += chunk.decode("utf-8", errors="replace")
            while True:
                stripped = buffer.lstrip()
                if not stripped:
                    buffer = ""
                    break
                try:
                    payload, index = decoder.raw_decode(stripped)
                except JSONDecodeError:
                    break
                if isinstance(payload, dict):
                    self._messages.put(_ACPResponse(payload=payload))
                buffer = stripped[index:]

    def _read_stderr(self) -> None:
        if self.process is None or self.process.stderr is None:
            return
        while True:
            if self.process is None or self.process.stderr is None:
                return
            chunk = os.read(self.process.stderr.fileno(), 4096)
            if not chunk:
                return
            self._stderr_chunks.append(chunk.decode("utf-8", errors="replace"))

    def _raise_rpc_error(self, response: _ACPResponse, method: str) -> None:
        error = response.error
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                raise ValueError(f"acp {method} failed: {message}")
        if error is not None:
            raise ValueError(f"acp {method} failed")

    def _build_timeout_error(self, method: str) -> str:
        stderr = "".join(self._stderr_chunks).strip()
        if stderr:
            return f"acp {method} failed: {stderr}"
        return f"acp {method} timed out"


def _build_acp_command(coco_bin: str, mode: _ACPMode, query_timeout: str) -> list[str]:
    cmd = [coco_bin, "acp", "serve"]
    if mode.yolo:
        cmd.append("--yolo")
    if query_timeout:
        cmd.extend(["--query-timeout", query_timeout])
    return cmd


def _parse_duration_seconds(value: str) -> float:
    normalized = value.strip()
    if not normalized:
        return 120.0
    matches = _DURATION_PART.findall(normalized)
    if not matches:
        return 120.0
    total = 0.0
    for amount_text, unit in matches:
        amount = int(amount_text)
        if unit == "ms":
            total += amount / 1000.0
        elif unit == "s":
            total += amount
        elif unit == "m":
            total += amount * 60
        elif unit == "h":
            total += amount * 3600
    return total or 120.0


_SESSION_POOL = _ACPSessionPool()


def run_prompt_with_pool(
    *,
    coco_bin: str,
    cwd: str,
    mode: str,
    query_timeout: str,
    prompt: str,
    idle_timeout_seconds: float,
    fresh_session: bool = False,
) -> str:
    resolved_mode = _resolve_mode(mode)
    return _SESSION_POOL.run_prompt(
        coco_bin=coco_bin,
        cwd=os.path.realpath(cwd),
        mode=resolved_mode,
        query_timeout=query_timeout,
        prompt=prompt,
        idle_timeout_seconds=idle_timeout_seconds,
        fresh_session=fresh_session,
    )


def new_session_with_pool(
    *,
    coco_bin: str,
    cwd: str,
    mode: str,
    query_timeout: str,
    idle_timeout_seconds: float,
    role: str,
) -> AgentSessionHandle:
    resolved_mode = _resolve_mode(mode)
    return _SESSION_POOL.new_session(
        coco_bin=coco_bin,
        cwd=os.path.realpath(cwd),
        mode=resolved_mode,
        query_timeout=query_timeout,
        idle_timeout_seconds=idle_timeout_seconds,
        role=role,
    )


def prompt_session_with_pool(*, handle_id: str, prompt: str) -> str:
    return _SESSION_POOL.prompt_session(handle_id, prompt)


def close_session_with_pool(*, handle_id: str) -> None:
    _SESSION_POOL.close_session(handle_id)


def _resolve_mode(mode: str) -> _ACPMode:
    if mode == AGENT_MODE.name:
        return AGENT_MODE
    raise ValueError(f"unknown acp mode: {mode}")


def _agent_session_handle_from_payload(payload: dict[str, object]) -> AgentSessionHandle:
    handle_id = payload.get("handle_id")
    cwd = payload.get("cwd")
    mode = payload.get("mode")
    query_timeout = payload.get("query_timeout")
    role = payload.get("role")
    if not isinstance(handle_id, str) or not handle_id.strip():
        raise ValueError("daemon session_new response missing handle_id")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("daemon session_new response missing cwd")
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError("daemon session_new response missing mode")
    if not isinstance(query_timeout, str) or not query_timeout.strip():
        raise ValueError("daemon session_new response missing query_timeout")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("daemon session_new response missing role")
    return AgentSessionHandle(
        handle_id=handle_id,
        cwd=cwd,
        mode=mode,
        query_timeout=query_timeout,
        role=role,
    )
