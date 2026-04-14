from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from coco_flow.config import Settings
from coco_flow.services.task_refine import refine_task


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
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class RefineTaskTest(unittest.TestCase):
    def test_pending_lark_source_keeps_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_id = "task-pending"
            task_dir = settings.task_root / task_id
            task_dir.mkdir(parents=True)
            now = datetime.now().astimezone().isoformat()
            (task_dir / "task.json").write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "title": "飞书需求",
                        "status": "initialized",
                        "created_at": now,
                        "updated_at": now,
                        "source_type": "lark_doc",
                        "source_value": "https://example.feishu.cn/wiki/abc123",
                        "repo_count": 1,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            (task_dir / "source.json").write_text(
                json.dumps(
                    {
                        "type": "lark_doc",
                        "title": "飞书需求",
                        "url": "https://example.feishu.cn/wiki/abc123",
                        "doc_token": "abc123",
                        "fetch_error": "lark-cli 不可用",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            (task_dir / "prd.source.md").write_text(
                "# PRD Source\n\n"
                "- source_type: lark_doc\n"
                "- url: https://example.feishu.cn/wiki/abc123\n"
                "- doc_token: abc123\n"
                "- fetched_at: 2026-04-14T00:00:00+08:00\n\n"
                "---\n\n"
                "尚未自动拉取该来源的正文内容，请稍后补充。\n"
            )

            status = refine_task(task_id, settings=settings)

            self.assertEqual(status, "initialized")
            refined = (task_dir / "prd-refined.md").read_text()
            self.assertIn("状态：待补充源内容", refined)
            self.assertIn("lark-cli 不可用", refined)
            task_meta = json.loads((task_dir / "task.json").read_text())
            self.assertEqual(task_meta["status"], "initialized")


if __name__ == "__main__":
    unittest.main()
