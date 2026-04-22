from __future__ import annotations

import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from coco_flow.cli import app


class CliRemoteCommandsTest(unittest.TestCase):
    def test_remote_add_and_list_delegate_to_runtime(self) -> None:
        runner = CliRunner()
        with (
            patch(
                "coco_flow.cli.remote_runtime.add_remote",
                return_value={
                    "name": "dev",
                    "host": "10.0.0.8",
                    "user": "maifeng",
                    "local_port": 4318,
                    "remote_port": 4318,
                    "updated": False,
                },
            ) as add_mock,
            patch(
                "coco_flow.cli.remote_runtime.list_remotes",
                return_value={
                    "remotes": [
                        {
                            "name": "dev",
                            "host": "10.0.0.8",
                            "user": "maifeng",
                            "local_port": 4318,
                            "remote_port": 4318,
                        }
                    ],
                    "config_path": "/tmp/remotes.json",
                },
            ) as list_mock,
        ):
            add_result = runner.invoke(app, ["remote", "add", "dev", "--host", "10.0.0.8", "--user", "maifeng"])
            list_result = runner.invoke(app, ["remote", "list"])

        self.assertEqual(add_result.exit_code, 0, msg=add_result.output)
        self.assertEqual(list_result.exit_code, 0, msg=list_result.output)
        add_mock.assert_called_once()
        list_mock.assert_called_once()
        self.assertIn("added: dev -> 10.0.0.8", add_result.output)
        self.assertIn("dev host=10.0.0.8 user=maifeng local=4318 remote=4318", list_result.output)

    def test_remote_connect_delegates_to_runtime(self) -> None:
        runner = CliRunner()
        with patch(
            "coco_flow.cli.remote_runtime.connect_remote",
            return_value={
                "target": "dev",
                "host": "10.0.0.8",
                "ssh_target": "maifeng@10.0.0.8",
                "local_url": "http://127.0.0.1:4318?coco_flow_context=remote&remote_name=dev&remote_host=10.0.0.8",
                "remote_started": False,
                "tunnel_started": False,
                "reused_local": True,
                "reused_remote": True,
            },
        ) as connect_mock:
            result = runner.invoke(app, ["remote", "connect", "dev", "--user", "maifeng"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        connect_mock.assert_called_once()
        self.assertIn("connected: maifeng@10.0.0.8", result.output)
        self.assertIn(
            "url: http://127.0.0.1:4318?coco_flow_context=remote&remote_name=dev&remote_host=10.0.0.8",
            result.output,
        )

    def test_remote_status_prints_empty_message(self) -> None:
        runner = CliRunner()
        with patch(
            "coco_flow.cli.remote_runtime.remote_status",
            return_value={"connections": [], "config_path": "/tmp/none.json", "remotes": []},
        ):
            result = runner.invoke(app, ["remote", "status"])

        self.assertEqual(result.exit_code, 0, msg=result.output)
        self.assertIn("no managed remote tunnels", result.output)


if __name__ == "__main__":
    unittest.main()
