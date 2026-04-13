from __future__ import annotations

from typing import TypedDict


class PromptRequest(TypedDict):
    type: str
    coco_bin: str
    cwd: str
    mode: str
    query_timeout: str
    prompt: str
    acp_idle_timeout_seconds: float


class PingRequest(TypedDict):
    type: str


class ShutdownRequest(TypedDict):
    type: str
