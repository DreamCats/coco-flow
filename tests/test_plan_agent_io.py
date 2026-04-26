from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coco_flow.clients import AgentSessionHandle
from coco_flow.config import Settings
from coco_flow.engines.plan.runtime import (
    close_plan_agent_session,
    new_plan_agent_session,
    run_plan_agent_markdown_with_new_session,
)
from coco_flow.engines.plan.types import PlanPreparedInput
from coco_flow.engines.shared.models import RefinedSections


class PlanAgentIOTest(unittest.TestCase):
    def test_standalone_bootstrap_prompts_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared = self._prepared(root)
            settings = self._settings(root)
            logs: list[str] = []

            with patch("coco_flow.engines.plan.runtime.agent.CocoACPClient", _FakeCocoACPClient):
                _FakeCocoACPClient.instances.clear()
                session = new_plan_agent_session(
                    prepared,
                    settings,
                    role="plan_reviewer",
                    on_log=logs.append,
                    bootstrap=True,
                )
                close_plan_agent_session(session, logs.append)

            client = _FakeCocoACPClient.instances[0]
            self.assertEqual(len(client.prompts), 1)
            self.assertIn("收到 bootstrap 后只需简短回复已完成", client.prompts[0])
            self.assertIn("Selected Plan skills", client.prompts[0])
            self.assertIn("bootstrap_prompt: true role=plan_reviewer", logs)
            self.assertIn("agent_prompt_start: role=plan_reviewer stage=bootstrap", logs)
            self.assertEqual(client.closed_roles, ["plan_reviewer"])

    def test_markdown_with_new_session_returns_normalized_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared = self._prepared(root)
            settings = self._settings(root)

            def prompt_builder(path: str) -> str:
                Path(path).write_text("# Plan\n", encoding="utf-8")
                return "write markdown"

            with patch("coco_flow.engines.plan.runtime.agent.CocoACPClient", _FakeCocoACPClient):
                _FakeCocoACPClient.instances.clear()
                markdown = run_plan_agent_markdown_with_new_session(
                    prepared,
                    settings,
                    "",
                    prompt_builder,
                    ".plan-writer-",
                    role="plan_writer",
                    stage="write",
                    on_log=lambda _line: None,
                )

            self.assertEqual(markdown, "# Plan\n")

    def _settings(self, root: Path) -> Settings:
        return Settings(
            config_root=root / "config",
            task_root=root / "tasks",
            refine_executor="local",
            plan_executor="native",
            code_executor="local",
            enable_go_test_verify=False,
            coco_bin="coco",
            native_query_timeout="10s",
            native_code_timeout="10s",
            acp_idle_timeout_seconds=60,
            daemon_idle_timeout_seconds=60,
        )

    def _prepared(self, root: Path) -> PlanPreparedInput:
        task_dir = root / "task"
        task_dir.mkdir()
        return PlanPreparedInput(
            task_dir=task_dir,
            task_id="task-1",
            title="测试 Plan agent_io",
            design_markdown="# Design",
            refined_markdown="# PRD",
            input_meta={},
            task_meta={},
            repos_meta={},
            repo_scopes=[],
            repo_ids=set(),
            refined_sections=RefinedSections(
                change_scope=[],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=[],
                open_questions=[],
                raw="# PRD",
            ),
            skills_brief_markdown="- plan skill brief",
            selected_skill_ids=["plan/test"],
        )


class _FakeCocoACPClient:
    instances: list["_FakeCocoACPClient"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.prompts: list[str] = []
        self.run_prompts: list[str] = []
        self.run_cwds: list[str] = []
        self.roles: list[str] = []
        self.closed_roles: list[str] = []
        self.instances.append(self)

    def run_agent(self, prompt: str, _query_timeout: str, *, cwd: str, fresh_session: bool) -> str:
        self.run_prompts.append(prompt)
        self.run_cwds.append(cwd)
        if not fresh_session:
            raise AssertionError("plan direct helper must request a fresh session")
        return "ok"

    def new_agent_session(self, *, query_timeout: str, cwd: str, role: str) -> AgentSessionHandle:
        self.roles.append(role)
        return AgentSessionHandle(
            handle_id=f"handle-{role}",
            cwd=cwd,
            mode="agent",
            query_timeout=query_timeout,
            role=role,
        )

    def prompt_agent_session(self, handle: AgentSessionHandle, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"ok:{handle.role}"

    def close_agent_session(self, handle: AgentSessionHandle) -> None:
        self.closed_roles.append(handle.role)


if __name__ == "__main__":
    unittest.main()
