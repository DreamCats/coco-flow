from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from coco_flow.api.presenters import task_detail_item
from coco_flow.config import Settings
from coco_flow.models.task import ArtifactItem, RepoBinding, TaskDetail, TimelineItem
from coco_flow.services.queries.task_detail import (
    build_next_action,
    build_task_detail,
    build_timeline,
    suggest_next_repo,
)
from coco_flow.services.queries.task_store import TaskStore


class TaskDetailPresenterTest(unittest.TestCase):
    def test_build_timeline_covers_designing_and_designed_with_six_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            (task_dir / "prd-refined.md").write_text("# PRD Refined\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# Design\n", encoding="utf-8")

            cases = [
                (
                    "designing",
                    ["done", "done", "current", "pending", "pending", "pending"],
                    {
                        "Design": "正在调研代码并生成 design.md",
                        "Plan": "等待 Design 产物就绪",
                    },
                ),
                (
                    "designed",
                    ["done", "done", "done", "current", "pending", "pending"],
                    {
                        "Design": "已生成 design.md",
                        "Plan": "等待生成 Plan 结构化产物",
                    },
                ),
            ]

            for status, states, details in cases:
                with self.subTest(status=status):
                    timeline = build_timeline(status, task_dir)
                    self.assertEqual(len(timeline), 6)
                    self.assertEqual([item.label for item in timeline], ["Input", "Refine", "Design", "Plan", "Code", "Archive"])
                    self.assertEqual([item.state for item in timeline], states)
                    for label, expected in details.items():
                        item = next(entry for entry in timeline if entry.label == label)
                        self.assertEqual(item.detail, expected)

    def test_suggest_next_repo_skips_blocked_repo(self) -> None:
        repos = [
            RepoBinding(repo_id="repo-b", path="/tmp/repo-b", status="planned", failure_type="blocked_by_dependency"),
            RepoBinding(repo_id="repo-a", path="/tmp/repo-a", status="planned"),
        ]
        self.assertEqual(suggest_next_repo(repos), "repo-a")

    def test_build_next_action_prefers_ready_repo_over_blocked_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            (task_dir / "prd-refined.md").write_text("# PRD Refined\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# Design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# Plan\n- complexity: 简单 (2)\n", encoding="utf-8")
            repos = [
                RepoBinding(repo_id="repo-b", path="/tmp/repo-b", status="planned", failure_type="blocked_by_dependency"),
                RepoBinding(repo_id="repo-a", path="/tmp/repo-a", status="planned"),
            ]
            action = build_next_action("task-1", "planned", task_dir, repos)
        self.assertEqual(action, "coco-flow tasks code task-1 --repo repo-a")

    def test_build_next_action_reports_blocked_when_no_ready_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            (task_dir / "prd-refined.md").write_text("# PRD Refined\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# Design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# Plan\n- complexity: 简单 (2)\n", encoding="utf-8")
            repos = [
                RepoBinding(repo_id="repo-b", path="/tmp/repo-b", status="planned", failure_type="blocked_by_dependency"),
            ]
            action = build_next_action("task-1", "planned", task_dir, repos)
        self.assertIn("受依赖阻塞", action)
        self.assertIn("repo-b", action)

    def test_build_timeline_reports_blocked_repos_in_planned_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "repo-b", "path": "/tmp/repo-b", "status": "planned"}]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            code_results = task_dir / "code-results"
            code_results.mkdir(parents=True)
            (code_results / "repo_b.json").write_text(
                json.dumps(
                    {
                        "repo_id": "repo-b",
                        "status": "planned",
                        "failure_type": "blocked_by_dependency",
                        "failure_action": "先推进 repo-a",
                        "error": "blocked by dependencies: repo-a",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            timeline = build_timeline("planned", task_dir)

        code_item = next(item for item in timeline if item.label == "Code")
        self.assertIn("受依赖阻塞", code_item.detail)
        self.assertIn("repo-b", code_item.detail)

    def test_task_detail_item_repo_next_skips_blocked_repo(self) -> None:
        detail = TaskDetail(
            task_id="task-1",
            title="demo",
            status="planned",
            created_at="2026-01-01T00:00:00+08:00",
            updated_at="2026-01-01T00:00:00+08:00",
            source_type="text",
            source_value="demo",
            repo_count=2,
            task_dir="/tmp/task-1",
            source_label="text",
            next_action="coco-flow tasks code task-1 --repo repo-a",
            repos=[
                RepoBinding(repo_id="repo-b", path="/tmp/repo-b", status="planned", failure_type="blocked_by_dependency"),
                RepoBinding(repo_id="repo-a", path="/tmp/repo-a", status="planned"),
            ],
            timeline=[TimelineItem(label="Code", state="current", detail="demo")],
            artifacts=[ArtifactItem(name="plan.md", path="/tmp/task-1/plan.md", exists=True, content="")],
        )

        payload = task_detail_item(detail)

        self.assertEqual(payload["repoNext"], ["repo-a"])

    def test_build_task_detail_exposes_code_v2_typed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": "task-1",
                        "title": "demo",
                        "status": "coding",
                        "source_type": "text",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "source.json").write_text(
                json.dumps({"type": "text"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (task_dir / "repos.json").write_text(
                json.dumps(
                    {
                        "repos": [
                            {
                                "id": "repo-a",
                                "path": "/tmp/repo-a",
                                "status": "coding",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "code-dispatch.json").write_text(
                json.dumps(
                    {
                        "batches": [
                            {
                                "batch_id": "batch-1",
                                "repo_id": "repo-a",
                                "execution_mode": "apply",
                                "scope_tier": "must_change",
                                "work_item_ids": ["W1", "W2"],
                                "depends_on_batch_ids": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "code-progress.json").write_text(
                json.dumps(
                    {
                        "status": "coding",
                        "summary": {
                            "total_batches": 1,
                            "completed_batches": 0,
                            "running_batches": 1,
                            "blocked_batches": 0,
                            "failed_batches": 0,
                            "total_work_items": 2,
                            "completed_work_items": 1,
                        },
                        "batches": [
                            {
                                "batch_id": "batch-1",
                                "repo_id": "repo-a",
                                "status": "running",
                                "work_item_ids": ["W1", "W2"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            code_results = task_dir / "code-results"
            code_results.mkdir(parents=True)
            (code_results / "repo_a.json").write_text(
                json.dumps(
                    {
                        "repo_id": "repo-a",
                        "status": "coding",
                        "build_ok": True,
                        "files_written": ["/tmp/repo-a/two_sum.go"],
                        "branch": "codex/task-1",
                        "commit": "abc123",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            code_verify = task_dir / "code-verify"
            code_verify.mkdir(parents=True)
            (code_verify / "repo_a.json").write_text(
                json.dumps(
                    {"status": "passed", "ok": True, "summary": "go build ./..."},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            diffs = task_dir / "diffs"
            diffs.mkdir(parents=True)
            (diffs / "repo_a.json").write_text(
                json.dumps(
                    {
                        "repo_id": "repo-a",
                        "commit": "abc123",
                        "branch": "codex/task-1",
                        "files": ["two_sum.go"],
                        "additions": 12,
                        "deletions": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (diffs / "repo_a.patch").write_text(
                "diff --git a/two_sum.go b/two_sum.go\n+package main\n",
                encoding="utf-8",
            )

            detail = build_task_detail(
                task_dir,
                "primary",
                json.loads((task_dir / "task.json").read_text(encoding="utf-8")),
                json.loads((task_dir / "source.json").read_text(encoding="utf-8")),
                json.loads((task_dir / "repos.json").read_text(encoding="utf-8")),
            )

        self.assertIsNotNone(detail.code_progress)
        self.assertIsNotNone(detail.code_dispatch)
        assert detail.code_dispatch is not None
        assert detail.code_progress is not None
        self.assertEqual(detail.code_dispatch.total_batches, 1)
        self.assertEqual(detail.code_dispatch.repo_ids, ["repo-a"])
        self.assertEqual(detail.code_dispatch.batch_ids, ["batch-1"])
        self.assertEqual(detail.code_progress.total_batches, 1)
        self.assertEqual(detail.code_progress.running_batches, 1)
        self.assertEqual(detail.code_progress.completed_work_items, 1)
        self.assertEqual(detail.repos[0].scope_tier, "must_change")
        self.assertEqual(detail.repos[0].execution_mode, "apply")
        self.assertEqual(detail.repos[0].batch_id, "batch-1")
        self.assertEqual(detail.repos[0].batch_status, "running")
        self.assertEqual(detail.repos[0].work_item_ids, ["W1", "W2"])
        self.assertEqual(detail.repos[0].files_written, ["two_sum.go"])
        self.assertEqual(detail.repos[0].verify_result, {"status": "passed", "ok": True, "summary": "go build ./..."})
        artifact_names = {artifact.name for artifact in detail.artifacts}
        self.assertIn("code-dispatch.json", artifact_names)
        self.assertIn("code-progress.json", artifact_names)

        payload = task_detail_item(detail)

        self.assertEqual(
            payload["codeDispatch"],
            {
                "totalBatches": 1,
                "repoIds": ["repo-a"],
                "batchIds": ["batch-1"],
            },
        )
        self.assertEqual(
            payload["codeProgress"],
            {
                "status": "coding",
                "totalBatches": 1,
                "completedBatches": 0,
                "runningBatches": 1,
                "blockedBatches": 0,
                "failedBatches": 0,
                "totalWorkItems": 2,
                "completedWorkItems": 1,
            },
        )
        self.assertEqual(payload["repos"][0]["scopeTier"], "must_change")
        self.assertEqual(payload["repos"][0]["executionMode"], "apply")
        self.assertEqual(payload["repos"][0]["batchId"], "batch-1")
        self.assertEqual(payload["repos"][0]["batchStatus"], "running")
        self.assertEqual(payload["repos"][0]["workItemIds"], ["W1", "W2"])
        self.assertEqual(payload["repos"][0]["verifyResult"], {"status": "passed", "ok": True, "summary": "go build ./..."})

    def test_task_store_reads_repo_code_verify_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_root = Path(tmp) / "tasks"
            task_root.mkdir(parents=True)
            task_dir = task_root / "task-1"
            task_dir.mkdir()
            (task_dir / "task.json").write_text(
                json.dumps({"task_id": "task-1", "title": "demo", "status": "planned"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            code_verify = task_dir / "code-verify"
            code_verify.mkdir(parents=True)
            expected = {"status": "failed", "ok": False, "summary": "go test failed"}
            (code_verify / "repo_a.json").write_text(
                json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            store = TaskStore(
                Settings(
                    config_root=Path(tmp),
                    task_root=task_root,
                    knowledge_root=Path(tmp) / "knowledge",
                    knowledge_executor="native",
                    refine_executor="native",
                    plan_executor="native",
                    code_executor="native",
                    enable_go_test_verify=False,
                    coco_bin="coco",
                    native_query_timeout="180s",
                    native_code_timeout="10m",
                    acp_idle_timeout_seconds=600,
                    daemon_idle_timeout_seconds=3600,
                )
            )

            content = store.get_artifact("task-1", "code-verify.json", repo_id="repo-a")

        self.assertEqual(content, json.dumps(expected, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
