from __future__ import annotations

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from coco_flow.cli import app


class CliRemoteCommandsTest(unittest.TestCase):
    def test_remote_connect_delegates_to_runtime(self) -> None:
        runner = CliRunner()
        with patch(
            "coco_flow.cli.remote_runtime.connect_remote",
            return_value={
                "target": "dev",
                "ssh_target": "maifeng@dev",
                "local_url": "http://127.0.0.1:4318",
                "remote_started": False,
                "tunnel_started": False,
                "reused_local": True,
                "reused_remote": True,
            },
        ) as connect_mock:
            result = runner.invoke(app, ["remote", "connect", "dev", "--user", "maifeng"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        connect_mock.assert_called_once()
        self.assertIn("connected: maifeng@dev", result.output)
        self.assertIn("url: http://127.0.0.1:4318", result.output)

    def test_remote_status_prints_empty_message(self) -> None:
        runner = CliRunner()
        with patch("coco_flow.cli.remote_runtime.remote_status", return_value={"connections": [], "config_path": "/tmp/none.json"}):
            result = runner.invoke(app, ["remote", "status"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("no managed remote tunnels", result.output)


if __name__ == "__main__":
    unittest.main()
