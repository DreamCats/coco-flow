from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.services.tasks.repos import update_task_repos


def make_settings(root: Path) -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor="local",
        plan_executor="local",
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class TaskRepoUpdateTest(unittest.TestCase):
    def test_update_task_repos_rewinds_downstream_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            repo_a = Path(tmp) / "repo-a"
            repo_b = Path(tmp) / "repo-b"
            for repo in (repo_a, repo_b):
                (repo / ".git").mkdir(parents=True)

            task_id = "task-repo-bind"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "repo bind demo",
                        "status": "planned",
                        "created_at": "2026-01-01T00:00:00+08:00",
                        "updated_at": "2026-01-01T00:00:00+08:00",
                        "source_type": "text",
                        "source_value": "demo",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "input.json").write_text(
                json.dumps({"title": "repo bind demo", "status": "planned"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (task_dir / "prd-refined.md").write_text("# PRD Refined\n\n- demo\n", encoding="utf-8")
            (task_dir / "design.md").write_text("# Design\n", encoding="utf-8")
            (task_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
            (task_dir / "design-research.json").write_text("{}\n", encoding="utf-8")
            (task_dir / "design-repo-responsibility-matrix.json").write_text("{}\n", encoding="utf-8")
            (task_dir / "plan-execution.json").write_text("{}\n", encoding="utf-8")
            (task_dir / "repos.json").write_text(
                json.dumps({"repos": [{"id": "repo-a", "path": str(repo_a), "status": "planned"}]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with patch(
                "coco_flow.services.tasks.repos.validate_repo_path",
                side_effect=lambda path: {"id": Path(path).name, "displayName": Path(path).name, "path": str(Path(path).resolve())},
            ):
                status = update_task_repos(task_id, [str(repo_a), str(repo_b)], settings=settings)

            self.assertEqual(status, "refined")
            task_meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(task_meta["status"], "refined")
            self.assertEqual(task_meta["repo_count"], 2)
            repos_meta = json.loads((task_dir / "repos.json").read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in repos_meta["repos"]], ["repo-a", "repo-b"])
            self.assertTrue(all(item["status"] == "refined" for item in repos_meta["repos"]))
            self.assertFalse((task_dir / "design.md").exists())
            self.assertFalse((task_dir / "plan.md").exists())
            self.assertFalse((task_dir / "design-research.json").exists())
            self.assertFalse((task_dir / "design-repo-responsibility-matrix.json").exists())
            self.assertFalse((task_dir / "plan-execution.json").exists())


if __name__ == "__main__":
    unittest.main()
