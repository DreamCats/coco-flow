from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

from typer.testing import CliRunner

from coco_flow.cli import app


def make_project_root(root: Path, with_git: bool = True, with_web: bool = True) -> Path:
    (root / "src" / "coco_flow").mkdir(parents=True, exist_ok=True)
    (root / "src" / "coco_flow" / "cli.py").write_text("app = None\n")
    (root / "pyproject.toml").write_text("[project]\nname='coco-flow'\n")
    if with_git:
        (root / ".git").write_text("gitdir: /tmp/fake\n")
    if with_web:
        (root / "web").mkdir(parents=True, exist_ok=True)
    return root.resolve()


class CliSetupCommandsTest(unittest.TestCase):
    def test_root_help_does_not_expose_prd_commands(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertNotIn("prd", result.output)

    def test_version_supports_json(self) -> None:
        runner = CliRunner()
        result = runner.invoke(app, ["version", "--json"])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn('"name": "coco-flow"', result.output)
        self.assertIn('"version":', result.output)

    def test_install_runs_uv_sync_and_ui_install_by_default(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            project_root = make_project_root(Path(tmp))
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            dir_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="/tmp/bin\n", stderr="")
            with patch("coco_flow.cli.subprocess.run", side_effect=[completed, completed, completed, completed, dir_completed]) as run_mock:
                result = runner.invoke(
                    app,
                    ["install", "--path", str(project_root)],
                )

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f"installed tool: coco-flow ({project_root})", result.output)
        self.assertIn("bin dir: /tmp/bin", result.output)
        self.assertEqual(
            run_mock.call_args_list,
            [
                call(["uv", "python", "install", "3.13"], cwd=project_root, check=False),
                call(["uv", "tool", "install", "--force", "--python", "3.13", "--editable", str(project_root)], cwd=project_root, check=False),
                call(["uv", "tool", "update-shell"], cwd=project_root, check=False),
                call(["npm", "install"], cwd=project_root / "web", check=False),
                call(["uv", "tool", "dir", "--bin"], cwd=project_root, check=False, capture_output=True, text=True),
            ],
        )

    def test_update_runs_git_pull_then_sync(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            project_root = make_project_root(Path(tmp))
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            dir_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="/tmp/bin\n", stderr="")
            with patch("coco_flow.cli.subprocess.run", side_effect=[completed, completed, completed, completed, completed, dir_completed]) as run_mock:
                result = runner.invoke(app, ["update", "--path", str(project_root)])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f"updated tool: coco-flow ({project_root})", result.output)
        self.assertIn("bin dir: /tmp/bin", result.output)
        self.assertEqual(
            run_mock.call_args_list,
            [
                call(["git", "pull", "--ff-only"], cwd=project_root, check=False),
                call(["uv", "python", "upgrade", "3.13"], cwd=project_root, check=False),
                call(["uv", "tool", "install", "--force", "--python", "3.13", "--editable", str(project_root)], cwd=project_root, check=False),
                call(["uv", "tool", "update-shell"], cwd=project_root, check=False),
                call(["npm", "install"], cwd=project_root / "web", check=False),
                call(["uv", "tool", "dir", "--bin"], cwd=project_root, check=False, capture_output=True, text=True),
            ],
        )

    def test_start_delegates_to_ui_serve(self) -> None:
        runner = CliRunner()
        with patch("coco_flow.cli.serve_ui") as serve_ui_mock:
            result = runner.invoke(app, ["start", "--no-build"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        serve_ui_mock.assert_called_once_with(host="127.0.0.1", port=4318, web_dir="", build_web=False)


if __name__ == "__main__":
    unittest.main()
