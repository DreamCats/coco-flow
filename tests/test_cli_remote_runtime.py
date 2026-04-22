from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.cli import remote_runtime
from coco_flow.config import Settings


class RemoteRuntimeTest(unittest.TestCase):
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

    def test_connect_reuses_matching_healthy_local_tunnel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            remote_runtime.add_remote("dev", host="10.0.0.8", user="maifeng", settings=settings)
            remote_runtime._save_remote_records(
                settings,
                [
                    {
                        "target": "dev",
                        "host": "10.0.0.8",
                        "user": "maifeng",
                        "local_port": 4318,
                        "remote_port": 4318,
                        "ssh_pid": 111,
                        "created_at": "2026-04-22T00:00:00+08:00",
                        "updated_at": "2026-04-22T00:00:00+08:00",
                    }
                ],
            )
            with (
                patch("coco_flow.cli.remote_runtime._probe_health", return_value=True),
                patch("coco_flow.cli.remote_runtime._probe_remote_health", return_value=True),
                patch(
                    "coco_flow.cli.remote_runtime.current_build_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch(
                    "coco_flow.cli.remote_runtime._fetch_remote_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch("coco_flow.cli.remote_runtime.webbrowser.open") as open_mock,
            ):
                result = remote_runtime.connect_remote("dev", user="maifeng", settings=settings)

        self.assertTrue(result["reused_local"])
        self.assertFalse(result["remote_started"])
        self.assertFalse(result["tunnel_started"])
        self.assertEqual(result["host"], "10.0.0.8")
        self.assertEqual(
            result["local_url"],
            "http://127.0.0.1:4318?coco_flow_context=remote&remote_name=dev&remote_host=10.0.0.8",
        )
        open_mock.assert_called_once_with(
            "http://127.0.0.1:4318?coco_flow_context=remote&remote_name=dev&remote_host=10.0.0.8"
        )

    def test_connect_starts_remote_and_tunnel_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            health_states = iter([False, False, True, True])
            with (
                patch("coco_flow.cli.remote_runtime._probe_health", side_effect=lambda *_args, **_kwargs: next(health_states)),
                patch("coco_flow.cli.remote_runtime._probe_remote_health", side_effect=[False, True]),
                patch(
                    "coco_flow.cli.remote_runtime.current_build_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch(
                    "coco_flow.cli.remote_runtime._fetch_remote_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch("coco_flow.cli.remote_runtime._start_remote_service") as start_remote_mock,
                patch("coco_flow.cli.remote_runtime._ensure_local_port_available") as ensure_port_mock,
                patch("coco_flow.cli.remote_runtime._start_tunnel", return_value=24680) as start_tunnel_mock,
                patch("coco_flow.cli.remote_runtime.webbrowser.open") as open_mock,
            ):
                result = remote_runtime.connect_remote("10.0.0.8", settings=settings)
                records = remote_runtime._load_remote_records(settings)

            self.assertTrue(result["remote_started"])
            self.assertTrue(result["tunnel_started"])
            start_remote_mock.assert_called_once()
            ensure_port_mock.assert_called_once_with(4318)
            start_tunnel_mock.assert_called_once()
            self.assertEqual(
                result["local_url"],
                "http://127.0.0.1:4318?coco_flow_context=remote&remote_name=10.0.0.8&remote_host=10.0.0.8",
            )
            open_mock.assert_called_once_with(
                "http://127.0.0.1:4318?coco_flow_context=remote&remote_name=10.0.0.8&remote_host=10.0.0.8"
            )
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["target"], "10.0.0.8")
            self.assertEqual(records[0]["host"], "10.0.0.8")
            self.assertEqual(records[0]["ssh_pid"], 24680)

    def test_disconnect_removes_matching_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            remote_runtime._save_remote_records(
                settings,
                [
                    {
                        "target": "dev",
                        "host": "dev",
                        "user": "",
                        "local_port": 4318,
                        "remote_port": 4318,
                        "ssh_pid": 123,
                        "created_at": "2026-04-22T00:00:00+08:00",
                        "updated_at": "2026-04-22T00:00:00+08:00",
                    },
                    {
                        "target": "sgdev",
                        "host": "sgdev",
                        "user": "",
                        "local_port": 5318,
                        "remote_port": 4318,
                        "ssh_pid": 456,
                        "created_at": "2026-04-22T00:00:00+08:00",
                        "updated_at": "2026-04-22T00:00:00+08:00",
                    },
                ],
            )
            with patch("coco_flow.cli.remote_runtime._terminate_process") as terminate_mock:
                result = remote_runtime.disconnect_remote("dev", settings=settings)
                remaining = remote_runtime._load_remote_records(settings)

            self.assertEqual(result["disconnected"], 1)
            terminate_mock.assert_called_once_with(123)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["target"], "sgdev")

    def test_add_list_remove_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            created = remote_runtime.add_remote(
                "dev",
                host="10.0.0.8",
                user="maifeng",
                local_port=4318,
                remote_port=5318,
                settings=settings,
            )
            listing = remote_runtime.list_remotes(settings=settings)
            removed = remote_runtime.remove_remote("dev", settings=settings)
            after = remote_runtime.list_remotes(settings=settings)

        self.assertFalse(created["updated"])
        self.assertEqual(created["name"], "dev")
        self.assertEqual(created["host"], "10.0.0.8")
        self.assertEqual(len(listing["remotes"]), 1)
        self.assertEqual(listing["remotes"][0]["name"], "dev")
        self.assertEqual(removed["removed"], "dev")
        self.assertEqual(after["remotes"], [])

    def test_connect_uses_saved_remote_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            remote_runtime.add_remote(
                "dev",
                host="10.0.0.8",
                user="maifeng",
                local_port=5318,
                remote_port=6318,
                settings=settings,
            )
            health_states = iter([False, False, True, True])
            with (
                patch("coco_flow.cli.remote_runtime._probe_health", side_effect=lambda *_args, **_kwargs: next(health_states)),
                patch("coco_flow.cli.remote_runtime._probe_remote_health", side_effect=[False, True]),
                patch(
                    "coco_flow.cli.remote_runtime.current_build_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch(
                    "coco_flow.cli.remote_runtime._fetch_remote_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch("coco_flow.cli.remote_runtime._start_remote_service") as start_remote_mock,
                patch("coco_flow.cli.remote_runtime._ensure_local_port_available") as ensure_port_mock,
                patch("coco_flow.cli.remote_runtime._start_tunnel", return_value=24680) as start_tunnel_mock,
                patch("coco_flow.cli.remote_runtime.webbrowser.open"),
            ):
                result = remote_runtime.connect_remote("dev", settings=settings)

        self.assertEqual(result["target"], "dev")
        self.assertEqual(result["host"], "10.0.0.8")
        start_remote_mock.assert_called_once_with("10.0.0.8", "maifeng", remote_port=6318, build_web=True)
        ensure_port_mock.assert_called_once_with(5318)
        start_tunnel_mock.assert_called_once_with("10.0.0.8", "maifeng", local_port=5318, remote_port=6318)

    def test_connect_logs_version_mismatch_when_remote_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.make_settings(Path(tmp))
            remote_runtime.add_remote("dev", host="10.0.0.8", user="maifeng", settings=settings)
            remote_runtime._save_remote_records(
                settings,
                [
                    {
                        "target": "dev",
                        "host": "10.0.0.8",
                        "user": "maifeng",
                        "local_port": 4318,
                        "remote_port": 4318,
                        "ssh_pid": 111,
                        "created_at": "2026-04-22T00:00:00+08:00",
                        "updated_at": "2026-04-22T00:00:00+08:00",
                    }
                ],
            )
            logs: list[str] = []
            with (
                patch("coco_flow.cli.remote_runtime._probe_health", return_value=True),
                patch("coco_flow.cli.remote_runtime._probe_remote_health", return_value=True),
                patch(
                    "coco_flow.cli.remote_runtime.current_build_meta",
                    return_value={"fingerprint": "git:local123", "version": "0.1.0"},
                ),
                patch(
                    "coco_flow.cli.remote_runtime._fetch_remote_meta",
                    return_value={"fingerprint": "git:remote999", "version": "0.1.0"},
                ),
                patch("coco_flow.cli.remote_runtime.webbrowser.open"),
            ):
                result = remote_runtime.connect_remote("dev", settings=settings, on_log=logs.append)

        self.assertFalse(result["fingerprint_match"])
        self.assertIn("remote_version_mismatch: local=git:local123 remote=git:remote999", logs)
        self.assertIn("remote_version_action: rerun with --restart after the remote machine has been updated", logs)


if __name__ == "__main__":
    unittest.main()
