from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

from typer.testing import CliRunner

from coco_flow.cli import app
from coco_flow.config import Settings


def make_project_root(root: Path, with_git: bool = True, with_web: bool = True) -> Path:
    (root / "src" / "coco_flow" / "cli").mkdir(parents=True, exist_ok=True)
    (root / "src" / "coco_flow" / "cli" / "__init__.py").write_text("app = None\n")
    (root / "pyproject.toml").write_text("[project]\nname='coco-flow'\n")
    if with_git:
        (root / ".git").write_text("gitdir: /tmp/fake\n")
    if with_web:
        (root / "web").mkdir(parents=True, exist_ok=True)
    return root.resolve()


class CliSetupCommandsTest(unittest.TestCase):
    def make_settings(self, root: Path) -> Settings:
        return Settings(
            config_root=root,
            task_root=root / "tasks",
            knowledge_root=root / "knowledge",
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
            with patch("coco_flow.cli.project.subprocess.run", side_effect=[completed, completed, completed, completed, dir_completed]) as run_mock:
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
            with patch("coco_flow.cli.project.subprocess.run", side_effect=[completed, completed, completed, completed, completed, dir_completed]) as run_mock:
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

    def test_update_defaults_to_installed_repo_root(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            project_root = make_project_root(Path(tmp))
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            dir_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="/tmp/bin\n", stderr="")
            with (
                patch("coco_flow.cli.project.installed_repo_root", return_value=project_root),
                patch("coco_flow.cli.project.subprocess.run", side_effect=[completed, completed, completed, completed, completed, dir_completed]) as run_mock,
            ):
                result = runner.invoke(app, ["update"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn(f"updated tool: coco-flow ({project_root})", result.output)
        self.assertEqual(run_mock.call_args_list[0], call(["git", "pull", "--ff-only"], cwd=project_root, check=False))

    def test_start_delegates_to_ui_serve(self) -> None:
        runner = CliRunner()
        with patch("coco_flow.cli.server.serve_ui") as serve_ui_mock:
            result = runner.invoke(app, ["start", "--no-build"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        serve_ui_mock.assert_called_once_with(host="0.0.0.0", port=4318, web_dir="", build_web=False)

    def test_start_detach_starts_background_server(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            settings = self.make_settings(config_root)
            proc = MagicMock()
            proc.pid = 12345
            proc.poll.return_value = None
            with (
                patch("coco_flow.cli.server.load_settings", return_value=settings),
                patch("coco_flow.cli.server.server_status", return_value={"running": False, "pid": None, "pid_file": "", "log_file": ""}),
                patch("coco_flow.cli.server.subprocess.Popen", return_value=proc) as popen_mock,
            ):
                result = runner.invoke(app, ["start", "--detach", "--no-build"])
                pid_text = (config_root / "server.pid").read_text().strip()

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("coco-flow server started in background", result.output)
        command = popen_mock.call_args.args[0]
        self.assertIn("run_background_server_entrypoint", command[2])
        self.assertIn("start", command)
        self.assertIn("--no-build", command)
        self.assertEqual(pid_text, "12345")

    def test_status_prints_server_state(self) -> None:
        runner = CliRunner()
        with patch(
            "coco_flow.cli.server.server_status",
            return_value={"running": True, "pid": 123, "pid_file": "/tmp/server.pid", "log_file": "/tmp/server.log"},
        ):
            result = runner.invoke(app, ["status"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn('"running": true', result.output)
        self.assertIn('"pid": 123', result.output)

    def test_stop_delegates_to_server_stop(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            with (
                patch("coco_flow.cli.commands.core.load_settings", return_value=settings),
                patch(
                    "coco_flow.cli.server.server_status",
                    return_value={"running": True, "pid": 123, "pid_file": "/tmp/server.pid", "log_file": "/tmp/server.log"},
                ),
                patch("coco_flow.cli.server.stop_server") as stop_server_mock,
            ):
                result = runner.invoke(app, ["stop"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("coco-flow server stopped", result.output)
        stop_server_mock.assert_called_once_with(settings)

    def test_ui_serve_prints_remote_access_hint(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            dist_dir = Path(tmp)
            (dist_dir / "index.html").write_text("<html></html>")
            with patch("coco_flow.cli.server.uvicorn.run") as uvicorn_run_mock:
                result = runner.invoke(app, ["ui", "serve", "--no-build", "--web-dir", str(dist_dir)])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("local: http://127.0.0.1:4318", result.output)
        self.assertIn("remote: http://<dev-machine-ip>:4318", result.output)
        self.assertIn("ssh -fN -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 -L 4318:127.0.0.1:4318 <user>@<dev-machine>", result.output)
        self.assertIn("pkill -f 'ssh .* -L 4318:127.0.0.1:4318 .*<user>@<dev-machine>'", result.output)
        self.assertIn("coco-flow start --detach", result.output)
        uvicorn_run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
