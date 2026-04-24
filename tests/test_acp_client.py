from __future__ import annotations

import unittest
from unittest.mock import patch

from coco_flow.clients.acp_client import AGENT_MODE, _ACPSessionPool


class _FakeACPProcess:
    instances: list["_FakeACPProcess"] = []

    def __init__(self, cmd: list[str], cwd: str, timeout_seconds: float) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        self.running = False
        self.session_counter = 0
        self.new_session_calls = 0
        self.prompt_calls: list[tuple[str, str]] = []
        _FakeACPProcess.instances.append(self)

    def start(self) -> None:
        self.running = True

    def initialize(self) -> None:
        return None

    def new_session(self, cwd: str) -> str:
        self.new_session_calls += 1
        self.session_counter += 1
        return f"session-{self.session_counter}"

    def prompt(self, session_id: str, prompt: str) -> str:
        self.prompt_calls.append((session_id, prompt))
        return f"reply:{session_id}"

    def is_running(self) -> bool:
        return self.running

    def close(self) -> None:
        self.running = False


class ACPSessionPoolTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeACPProcess.instances = []

    def test_run_prompt_reuses_existing_session_by_default(self) -> None:
        pool = _ACPSessionPool()
        with patch("coco_flow.clients.acp_client._ACPProcess", _FakeACPProcess):
            first = pool.run_prompt(
                coco_bin="coco",
                cwd="/tmp/demo",
                mode=AGENT_MODE,
                query_timeout="90s",
                prompt="first",
                idle_timeout_seconds=600.0,
            )
            second = pool.run_prompt(
                coco_bin="coco",
                cwd="/tmp/demo",
                mode=AGENT_MODE,
                query_timeout="90s",
                prompt="second",
                idle_timeout_seconds=600.0,
            )

        self.assertEqual(first, "reply:session-1")
        self.assertEqual(second, "reply:session-1")
        self.assertEqual(len(_FakeACPProcess.instances), 1)
        process = _FakeACPProcess.instances[0]
        self.assertEqual(process.new_session_calls, 1)
        self.assertEqual(
            process.prompt_calls,
            [("session-1", "first"), ("session-1", "second")],
        )

    def test_run_prompt_can_force_fresh_session_without_new_process(self) -> None:
        pool = _ACPSessionPool()
        with patch("coco_flow.clients.acp_client._ACPProcess", _FakeACPProcess):
            pooled = pool.run_prompt(
                coco_bin="coco",
                cwd="/tmp/demo",
                mode=AGENT_MODE,
                query_timeout="10m",
                prompt="pooled",
                idle_timeout_seconds=600.0,
            )
            fresh = pool.run_prompt(
                coco_bin="coco",
                cwd="/tmp/demo",
                mode=AGENT_MODE,
                query_timeout="10m",
                prompt="fresh",
                idle_timeout_seconds=600.0,
                fresh_session=True,
            )

        self.assertEqual(pooled, "reply:session-1")
        self.assertEqual(fresh, "reply:session-2")
        self.assertEqual(len(_FakeACPProcess.instances), 1)
        process = _FakeACPProcess.instances[0]
        self.assertEqual(process.new_session_calls, 2)
        self.assertEqual(
            process.prompt_calls,
            [("session-1", "pooled"), ("session-2", "fresh")],
        )

    def test_explicit_session_handle_supports_multiple_prompts(self) -> None:
        pool = _ACPSessionPool()
        with patch("coco_flow.clients.acp_client._ACPProcess", _FakeACPProcess):
            handle = pool.new_session(
                coco_bin="coco",
                cwd="/tmp/demo",
                mode=AGENT_MODE,
                query_timeout="180s",
                idle_timeout_seconds=600.0,
                role="refine_generate",
            )
            first = pool.prompt_session(handle.handle_id, "bootstrap")
            second = pool.prompt_session(handle.handle_id, "generate")

        self.assertEqual(handle.role, "refine_generate")
        self.assertEqual(first, "reply:session-2")
        self.assertEqual(second, "reply:session-2")
        self.assertEqual(len(_FakeACPProcess.instances), 1)
        process = _FakeACPProcess.instances[0]
        self.assertEqual(process.new_session_calls, 2)
        self.assertEqual(
            process.prompt_calls,
            [("session-2", "bootstrap"), ("session-2", "generate")],
        )

    def test_closed_explicit_session_handle_cannot_prompt(self) -> None:
        pool = _ACPSessionPool()
        with patch("coco_flow.clients.acp_client._ACPProcess", _FakeACPProcess):
            handle = pool.new_session(
                coco_bin="coco",
                cwd="/tmp/demo",
                mode=AGENT_MODE,
                query_timeout="180s",
                idle_timeout_seconds=600.0,
                role="refine_verify",
            )
            pool.close_session(handle.handle_id)
            with self.assertRaisesRegex(ValueError, "unknown acp session handle"):
                pool.prompt_session(handle.handle_id, "verify")


if __name__ == "__main__":
    unittest.main()
