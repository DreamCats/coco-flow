from __future__ import annotations

from typing import NotRequired, TypedDict


class PromptRequest(TypedDict):
    type: str
    coco_bin: str
    cwd: str
    mode: str
    query_timeout: str
    prompt: str
    acp_idle_timeout_seconds: float
    fresh_session: NotRequired[bool]


class PromptStreamRequest(PromptRequest):
    pass


class SessionNewRequest(TypedDict):
    type: str
    coco_bin: str
    cwd: str
    mode: str
    query_timeout: str
    acp_idle_timeout_seconds: float
    role: str


class SessionPromptRequest(TypedDict):
    type: str
    handle_id: str
    prompt: str


class SessionPromptStreamRequest(SessionPromptRequest):
    pass


class SessionCloseRequest(TypedDict):
    type: str
    handle_id: str


class PingRequest(TypedDict):
    type: str


class ShutdownRequest(TypedDict):
    type: str


class StreamChunkEvent(TypedDict):
    type: str
    content: str


class StreamDoneEvent(TypedDict):
    type: str
    content: str


class StreamErrorEvent(TypedDict):
    type: str
    error: str
