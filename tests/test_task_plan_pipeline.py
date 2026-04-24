from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.engines.design.pipeline import apply_review_issues_to_decision, normalize_decision_for_gate
from coco_flow.services.tasks.design import design_task
from coco_flow.services.tasks.plan import start_planning_task


def make_settings(root: Path, *, plan_executor: str = "local") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor="local",
        plan_executor=plan_executor,
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class DesignV3PipelineTest(unittest.TestCase):
    def test_revision_removes_blocked_candidate_file(self) -> None:
        decision = {
            "repo_decisions": [
                {
                    "repo_id": "demo",
                    "work_type": "must_change",
                    "candidate_files": ["src/right.py", "src/wrong.py"],
                    "candidate_dirs": ["src"],
                }
            ]
        }
        review = {
            "issues": [
                {
                    "severity": "blocking",
                    "failure_type": "candidate_file_not_proven",
                    "target": "src/wrong.py",
                    "suggested_action": "remove wrong candidate",
                }
            ]
        }

        revised, resolutions = apply_review_issues_to_decision(decision, review)

        repo = revised["repo_decisions"][0]
        self.assertEqual(repo["candidate_files"], ["src/right.py"])
        self.assertEqual(resolutions[0]["resolution"], "accepted")

    def test_validate_only_decision_does_not_expose_candidate_files(self) -> None:
        decision = {
            "repo_decisions": [
                {
                    "repo_id": "demo",
                    "work_type": "validate_only",
                    "candidate_files": ["src/noisy.py"],
                    "candidate_dirs": ["src"],
                }
            ]
        }

        normalized = normalize_decision_for_gate(decision, {"issues": []})

        repo = normalized["repo_decisions"][0]
        self.assertEqual(repo["candidate_files"], [])
        self.assertEqual(repo["candidate_dirs"], [])

    def test_local_design_v3_writes_agentic_artifacts_and_blocks_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="local")
            task_dir, _repo_dir = self._create_refined_task(settings.task_root, "task-design-v3")

            status = design_task("task-design-v3", settings=settings)

            self.assertEqual(status, "failed")
            self.assertTrue((task_dir / "design-input.json").exists())
            self.assertTrue((task_dir / "design-research-plan.json").exists())
            self.assertTrue((task_dir / "design-research" / "demo.json").exists())
            self.assertTrue((task_dir / "design-research-summary.json").exists())
            self.assertTrue((task_dir / "design-adjudication.json").exists())
            self.assertTrue((task_dir / "design-review.json").exists())
            self.assertTrue((task_dir / "design-debate.json").exists())
            self.assertTrue((task_dir / "design-decision.json").exists())
            self.assertTrue((task_dir / "design-repo-binding.json").exists())
            self.assertTrue((task_dir / "design-sections.json").exists())
            self.assertTrue((task_dir / "design.md").exists())
            self.assertTrue((task_dir / "design-verify.json").exists())
            self.assertTrue((task_dir / "design-diagnosis.json").exists())

            result = self._read_json(task_dir / "design-result.json")
            self.assertEqual(result["gate_status"], "degraded")
            self.assertEqual(result["plan_allowed"], False)
            with self.assertRaisesRegex(ValueError, "does not allow plan"):
                start_planning_task("task-design-v3", settings=settings)

    def test_design_v3_requires_bound_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root, plan_executor="local")
            task_dir = settings.task_root / "task-no-repo"
            task_dir.mkdir(parents=True)
            self._write_json(task_dir / "task.json", {"task_id": "task-no-repo", "title": "No repo", "status": "refined"})
            self._write_json(task_dir / "input.json", {})
            self._write_json(task_dir / "repos.json", {"repos": []})
            (task_dir / "prd-refined.md").write_text("# PRD\n\n## 本次范围\n- 更新成功态。\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "design requires bound repos"):
                design_task("task-no-repo", settings=settings)

    def _create_refined_task(self, task_root: Path, task_id: str) -> tuple[Path, Path]:
        repo_dir = task_root.parent / "demo-repo"
        repo_dir.mkdir(parents=True)
        (repo_dir / "status.py").write_text(
            "def success_status():\n    return 'success'\n",
            encoding="utf-8",
        )
        task_dir = task_root / task_id
        task_dir.mkdir(parents=True)
        self._write_json(task_dir / "task.json", {"task_id": task_id, "title": "成功态状态提示", "status": "refined"})
        self._write_json(task_dir / "input.json", {"title": "成功态状态提示"})
        self._write_json(task_dir / "refine-brief.json", {"change_points": ["成功态状态提示"]})
        self._write_json(task_dir / "refine-intent.json", {})
        self._write_json(task_dir / "repos.json", {"repos": [{"id": "demo", "path": str(repo_dir), "status": "refined"}]})
        (task_dir / "prd-refined.md").write_text(
            "# PRD\n\n## 本次范围\n- 成功态状态提示需要落到 success_status。\n\n## 验收标准\n- success 状态展示正确。\n",
            encoding="utf-8",
        )
        return task_dir, repo_dir

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
