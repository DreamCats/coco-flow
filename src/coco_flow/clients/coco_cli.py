from __future__ import annotations

import json
import subprocess

from .base import CocoClient


class CocoCliClient(CocoClient):
    def __init__(self, coco_bin: str) -> None:
        self.coco_bin = coco_bin

    def run_agent(
        self,
        prompt: str,
        query_timeout: str,
        cwd: str,
        *,
        fresh_session: bool = False,
    ) -> str:
        cmd = [
            self.coco_bin,
            "-p",
            "--json",
            "--yolo",
            "--query-timeout",
            query_timeout,
            prompt,
        ]
        return self._run_json_command(cmd, cwd=cwd)

    def _run_json_command(self, cmd: list[str], cwd: str | None = None) -> str:
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise ValueError(f"native coco executable not found: {self.coco_bin}") from error

        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or "native coco command failed")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("native coco returned non-JSON output") from error

        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("native coco response missing message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("native coco response missing content")
        return content.strip()
