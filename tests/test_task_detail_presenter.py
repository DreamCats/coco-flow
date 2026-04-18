from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from coco_flow.api.presenters import task_detail_item
from coco_flow.models.task import ArtifactItem, RepoBinding, TaskDetail, TimelineItem
from coco_flow.services.queries.task_detail import build_next_action, build_timeline, suggest_next_repo


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
        self.assertEqual(action, "coco-flow prd code --task task-1 --repo repo-a")

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
            next_action="coco-flow prd code --task task-1 --repo repo-a",
            repos=[
                RepoBinding(repo_id="repo-b", path="/tmp/repo-b", status="planned", failure_type="blocked_by_dependency"),
                RepoBinding(repo_id="repo-a", path="/tmp/repo-a", status="planned"),
            ],
            timeline=[TimelineItem(label="Code", state="current", detail="demo")],
            artifacts=[ArtifactItem(name="plan.md", path="/tmp/task-1/plan.md", exists=True, content="")],
        )

        payload = task_detail_item(detail)

        self.assertEqual(payload["repoNext"], ["repo-a"])


if __name__ == "__main__":
    unittest.main()
