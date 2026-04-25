from __future__ import annotations

from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.engines.code.dispatch import build_code_runtime_state
from coco_flow.engines.code.models import CodePreparedInput, CodeRepoBatch
from coco_flow.prompts.code import build_code_execute_prompt
from coco_flow.services.runtime.repo_state import read_repo_code_result
from coco_flow.services.tasks.code import code_task, start_coding_task


def make_settings(root: Path, *, code_executor: str = "native") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor="local",
        plan_executor="local",
        code_executor=code_executor,
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class CodeV2DispatchTest(unittest.TestCase):
    def test_start_coding_blocks_when_plan_gate_disallows_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            task_id = "task-blocked-plan"
            task_dir = settings.task_root / task_id
            repo_root = root / "repo"
            task_dir.mkdir(parents=True)
            repo_root.mkdir()
            (task_dir / "task.json").write_text(
                json.dumps({"task_id": task_id, "title": "blocked", "status": "planned"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "input.json").write_text("{}\n", encoding="utf-8")
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "demo", "path": str(repo_root), "status": "planned"}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "design-repo-binding.json").write_text(
                json.dumps({"repo_bindings": [{"repo_id": "demo", "decision": "in_scope", "scope_tier": "must_change"}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-work-items.json").write_text(
                json.dumps({"work_items": [{"id": "W1", "repo_id": "demo", "title": "demo"}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-execution-graph.json").write_text(
                json.dumps({"nodes": ["W1"], "edges": [], "execution_order": ["W1"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-validation.json").write_text(
                json.dumps({"task_validations": [{"task_id": "W1", "repo_id": "demo", "checks": []}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-result.json").write_text(
                json.dumps({"status": "failed", "gate_status": "needs_human", "code_allowed": False}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text("# refined\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# plan\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not allow code"):
                start_coding_task(task_id, settings=settings)

    def test_start_coding_blocks_when_plan_markdown_is_unsynced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            task_id = "task-unsynced-plan"
            task_dir = settings.task_root / task_id
            repo_root = root / "repo"
            task_dir.mkdir(parents=True)
            repo_root.mkdir()
            (task_dir / "task.json").write_text(
                json.dumps({"task_id": task_id, "title": "unsynced", "status": "planned"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "input.json").write_text("{}\n", encoding="utf-8")
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "demo", "path": str(repo_root), "status": "planned"}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-work-items.json").write_text(
                json.dumps({"work_items": [{"id": "W1", "repo_id": "demo", "title": "demo"}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-execution-graph.json").write_text(
                json.dumps({"nodes": ["W1"], "edges": [], "execution_order": ["W1"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-validation.json").write_text(
                json.dumps({"task_validations": [{"task_id": "W1", "repo_id": "demo", "checks": []}]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-sync.json").write_text(
                json.dumps({"synced": False, "changed_artifact": "plan.md", "repo_id": "demo"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-result.json").write_text(
                json.dumps({"status": "planned", "gate_status": "passed", "code_allowed": True}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text("# refined\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# plan\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Re-run Plan before Code"):
                start_coding_task(task_id, settings=settings)

    def test_dispatch_uses_plan_v2_artifacts_and_skips_reference_only_repo(self) -> None:
        prepared = CodePreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task-1",
            title="demo",
            task_meta={},
            repos_meta={
                "repos": [
                    {"id": "demo", "path": "/tmp/demo", "status": "planned"},
                    {"id": "verify", "path": "/tmp/verify", "status": "planned"},
                    {"id": "docs", "path": "/tmp/docs", "status": "planned"},
                ]
            },
            design_repo_binding_payload={
                "repo_bindings": [
                    {"repo_id": "demo", "decision": "in_scope", "scope_tier": "must_change", "candidate_files": ["two_sum.py"], "candidate_dirs": []},
                    {"repo_id": "verify", "decision": "in_scope", "scope_tier": "validate_only", "candidate_files": ["README.md"], "candidate_dirs": []},
                    {"repo_id": "docs", "decision": "in_scope", "scope_tier": "reference_only", "candidate_files": ["docs.md"], "candidate_dirs": []},
                ]
            },
            plan_work_items_payload={
                "work_items": [
                    {
                        "id": "W1",
                        "title": "实现 two sum",
                        "repo_id": "demo",
                        "goal": "实现算法",
                        "change_scope": ["two_sum.py"],
                        "done_definition": ["实现 two sum"],
                        "verification_steps": ["python py_compile"],
                        "depends_on": [],
                    }
                ]
            },
            plan_execution_graph_payload={"execution_order": ["W1"], "edges": []},
            plan_validation_payload={
                "global_validation_focus": ["最小 py_compile 通过"],
                "task_validations": [
                    {"task_id": "W1", "repo_id": "demo", "checks": [{"reason": "python py_compile"}]}
                ],
            },
            plan_result_payload={"status": "planned"},
            refined_markdown="# PRD Refined\n",
            design_markdown="# Design\n",
            plan_markdown="# Plan\n",
        )

        runtime = build_code_runtime_state(prepared)
        batches = runtime.batches
        payload = runtime.dispatch_payload

        self.assertEqual([batch.repo_id for batch in batches], ["demo", "verify"])
        self.assertEqual([batch.execution_mode for batch in batches], ["apply", "verify_only"])
        self.assertEqual(payload["batches"][0]["work_item_ids"], ["W1"])

    def test_dispatch_does_not_promote_design_candidate_files_into_change_scope(self) -> None:
        prepared = CodePreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task-1",
            title="demo",
            task_meta={},
            repos_meta={
                "repos": [
                    {"id": "demo", "path": "/tmp/demo", "status": "planned"},
                ]
            },
            design_repo_binding_payload={
                "repo_bindings": [
                    {
                        "repo_id": "demo",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "candidate_files": ["existing_reference.py"],
                        "candidate_dirs": [],
                    }
                ]
            },
            plan_work_items_payload={
                "work_items": [
                    {
                        "id": "W1",
                        "title": "实现 two sum",
                        "repo_id": "demo",
                        "goal": "实现算法",
                        "change_scope": [],
                        "done_definition": ["实现 two sum"],
                        "verification_steps": ["python py_compile"],
                        "depends_on": [],
                    }
                ]
            },
            plan_execution_graph_payload={"execution_order": ["W1"], "edges": []},
            plan_validation_payload={"task_validations": []},
            plan_result_payload={"status": "planned"},
            refined_markdown="# PRD Refined\n",
            design_markdown="# Design\n",
            plan_markdown="# Plan\n",
        )

        runtime = build_code_runtime_state(prepared)

        self.assertEqual(runtime.batches[0].change_scope, [])
        self.assertEqual(runtime.dispatch_payload["batches"][0]["change_scope"], [])

    def test_execute_prompt_references_code_batch_bundle_not_full_plan_payloads(self) -> None:
        prepared = CodePreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task-2",
            title="demo",
            task_meta={},
            repos_meta={"repos": []},
            design_repo_binding_payload={},
            plan_work_items_payload={
                "work_items": [
                    {
                        "id": "W1",
                        "title": "实现 two sum",
                        "repo_id": "demo",
                        "goal": "实现算法",
                        "change_scope": ["two_sum.py"],
                        "done_definition": ["实现 two sum"],
                        "verification_steps": ["python py_compile"],
                    }
                ]
            },
            plan_execution_graph_payload={},
            plan_validation_payload={},
            plan_result_payload={"status": "planned"},
            refined_markdown="# PRD Refined\n",
            design_markdown="# Design\n",
            plan_markdown="# Plan\n",
        )
        batch = CodeRepoBatch(
            id="B1",
            repo_id="demo",
            repo_path="/tmp/demo",
            scope_tier="must_change",
            execution_mode="apply",
            work_item_ids=["W1"],
            depends_on_batch_ids=[],
            blocked_by_batch_ids=[],
            change_scope=["two_sum.py"],
            verify_rules=["python py_compile"],
            done_definition=["实现 two sum"],
            status="ready",
            summary="",
        )

        prompt = build_code_execute_prompt(
            task_id=prepared.task_id,
            repo_id=batch.repo_id,
            execution_mode=batch.execution_mode,
            work_item_brief="- W1 实现 two sum",
            change_scope_brief="- two_sum.py",
            verify_brief="- python py_compile",
            dependency_brief="- 当前 batch 无 batch 级前置依赖。",
        )

        self.assertIn("code-batch.json", prompt)
        self.assertIn("code-batch.md", prompt)
        self.assertIn("prd-refined.md", prompt)
        self.assertIn("design.md", prompt)
        self.assertIn("plan.md", prompt)
        self.assertNotIn("plan-work-items.json", prompt)
        self.assertNotIn("plan-execution-graph.json", prompt)
        self.assertNotIn("plan-validation.json", prompt)
        self.assertNotIn("plan-result.json", prompt)
        self.assertNotIn("plan-execution.json", prompt)


class CodeV2PipelineIntegrationTest(unittest.TestCase):
    def test_code_task_writes_dispatch_progress_and_repo_result_from_plan_v2_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, code_executor="native")
            repo_root = root / "repo"
            self._init_git_repo(repo_root)

            task_id = "task-code-v2"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = "2026-04-19T00:00:00+08:00"
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "实现 two sum",
                        "status": "planned",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "text",
                        "source_value": "实现 two sum",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps(
                    {"repos": [{"id": "demo", "path": str(repo_root), "status": "planned"}]},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "design-repo-binding.json").write_text(
                json.dumps(
                    {
                        "repo_bindings": [
                            {
                                "repo_id": "demo",
                                "repo_path": str(repo_root),
                                "decision": "in_scope",
                                "scope_tier": "must_change",
                                "candidate_files": ["two_sum.py"],
                                "candidate_dirs": [],
                                "change_summary": ["新增 two sum 算法文件"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-work-items.json").write_text(
                json.dumps(
                    {
                        "work_items": [
                            {
                                "id": "W1",
                                "title": "实现 two sum",
                                "repo_id": "demo",
                                "goal": "新增 two sum Python 实现",
                                "change_scope": ["two_sum.py"],
                                "done_definition": ["实现 two sum", "最小 py_compile 通过"],
                                "verification_steps": ["python py_compile"],
                                "depends_on": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-execution-graph.json").write_text(
                json.dumps(
                    {"nodes": ["W1"], "edges": [], "execution_order": ["W1"], "parallel_groups": [], "critical_path": ["W1"], "coordination_points": []},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-validation.json").write_text(
                json.dumps(
                    {
                        "global_validation_focus": ["two sum py_compile"],
                        "task_validations": [
                            {
                                "task_id": "W1",
                                "repo_id": "demo",
                                "checks": [{"kind": "review", "target": "demo", "reason": "python py_compile"}],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "plan-result.json").write_text('{"status":"planned"}\n', encoding="utf-8")
            (task_dir / "prd-refined.md").write_text("# refined\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# plan\n", encoding="utf-8")

            start_status = start_coding_task(task_id, settings=settings)
            self.assertEqual(start_status, "coding")
            self.assertTrue((task_dir / "code-dispatch.json").exists())
            self.assertTrue((task_dir / "code-progress.json").exists())
            self.assertFalse((task_dir / "plan-execution.json").exists())

            def fake_run_agent(prompt: str, query_timeout: str, cwd: str, *, fresh_session: bool = False) -> str:
                Path(cwd, "two_sum.py").write_text(
                    "def two_sum(nums, target):\n"
                    "    seen = {}\n"
                    "    for index, value in enumerate(nums):\n"
                    "        if target - value in seen:\n"
                    "            return [seen[target - value], index]\n"
                    "        seen[value] = index\n"
                    "    return []\n",
                    encoding="utf-8",
                )
                return "=== CODE RESULT ===\nstatus: success\nsummary: implemented two sum\nfiles:\n- two_sum.py\n"

            with patch("coco_flow.clients.CocoACPClient.run_agent", side_effect=fake_run_agent):
                status = code_task(task_id, settings=settings, allow_coding_targets=True)

            self.assertEqual(status, "coded")
            dispatch = json.loads((task_dir / "code-dispatch.json").read_text(encoding="utf-8"))
            self.assertEqual(dispatch["batches"][0]["repo_id"], "demo")
            self.assertEqual(dispatch["batches"][0]["execution_mode"], "apply")
            progress = json.loads((task_dir / "code-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["completed_batches"], ["B1"])
            task_result = json.loads((task_dir / "code-result.json").read_text(encoding="utf-8"))
            self.assertEqual(task_result["status"], "coded")
            repo_result = read_repo_code_result(task_dir, "demo")
            self.assertEqual(repo_result["repo_id"], "demo")
            self.assertTrue(repo_result["commit"])
            self.assertEqual(repo_result["files_written"], ["two_sum.py"])
            self.assertTrue((task_dir / "code-verify" / "demo.json").exists())
            worktree_root = Path(repo_result["worktree"])
            batch_bundle = worktree_root / ".coco-flow" / "tasks" / task_id / "code-batch.json"
            batch_markdown = worktree_root / ".coco-flow" / "tasks" / task_id / "code-batch.md"
            self.assertTrue(batch_bundle.exists())
            self.assertTrue(batch_markdown.exists())
            self.assertFalse((worktree_root / ".coco-flow" / "tasks" / task_id / "plan-work-items.json").exists())
            batch_payload = json.loads(batch_bundle.read_text(encoding="utf-8"))
            self.assertEqual(batch_payload["repo_id"], "demo")
            self.assertEqual(batch_payload["work_item_ids"], ["W1"])

    def _init_git_repo(self, repo_root: Path) -> None:
        repo_root.mkdir(parents=True, exist_ok=True)
        (repo_root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo_root, check=True, capture_output=True, text=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=tester",
                "-c",
                "user.email=tester@example.com",
                "commit",
                "-m",
                "init",
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
