from __future__ import annotations

from typing import Protocol


class CocoClient(Protocol):
    def run_agent(
        self,
        prompt: str,
        query_timeout: str,
        cwd: str,
        *,
        fresh_session: bool = False,
    ) -> str: ...
