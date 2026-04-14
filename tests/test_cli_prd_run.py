from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from coco_flow.cli import app
from coco_flow.config import Settings


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


class PrdRunCommandTest(unittest.TestCase):
    def test_prd_run_stops_before_code_when_plan_is_complex(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            with (
                patch("coco_flow.cli.load_settings", return_value=settings),
                patch("coco_flow.cli.create_task", return_value=("task-1", "initialized")) as create_task_mock,
                patch("coco_flow.cli.refine_task", return_value="refined") as refine_task_mock,
                patch("coco_flow.cli.plan_task", return_value="planned") as plan_task_mock,
                patch("coco_flow.cli.read_task_complexity", return_value="复杂"),
                patch("coco_flow.cli.code_task") as code_task_mock,
            ):
                result = runner.invoke(app, ["prd", "run", "-i", "需求描述"])

            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertIn("task_id: task-1", result.output)
            self.assertIn("refine: refined", result.output)
            self.assertIn("plan: planned", result.output)
            self.assertIn("plan complexity=复杂，run 停止在 plan 阶段。", result.output)
            create_task_mock.assert_called_once()
            refine_task_mock.assert_called_once()
            plan_task_mock.assert_called_once()
            code_task_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
