from __future__ import annotations

from typing import Protocol


class CocoClient(Protocol):
    def run_prompt_only(self, prompt: str, query_timeout: str, cwd: str | None = None) -> str: ...

    def run_readonly_agent(self, prompt: str, query_timeout: str, cwd: str) -> str: ...

    def run_agent(self, prompt: str, query_timeout: str, cwd: str) -> str: ...
