from __future__ import annotations

from typing import Protocol


class CocoClient(Protocol):
    def run_prompt_only(
        self,
        prompt: str,
        query_timeout: str,
        cwd: str | None = None,
        *,
        fresh_session: bool = False,
    ) -> str: ...

    def run_readonly_agent(
        self,
        prompt: str,
        query_timeout: str,
        cwd: str,
        *,
        fresh_session: bool = False,
    ) -> str: ...

    def run_agent(
        self,
        prompt: str,
        query_timeout: str,
        cwd: str,
        *,
        fresh_session: bool = False,
    ) -> str: ...
