from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.services.tasks.input import create_task, input_task


def make_settings(root: Path) -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    knowledge_root = config_root / "knowledge"
    task_root.mkdir(parents=True, exist_ok=True)
    knowledge_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        knowledge_root=knowledge_root,
        knowledge_executor="local",
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


class InputTaskTest(unittest.TestCase):
    def test_create_long_text_input_does_not_try_treat_as_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            long_input = "# PRD\n\n" + ("竞拍讲解卡成交后展示独立 Success 态\n" * 40)

            task_id, status = create_task(
                raw_input=long_input,
                title="长文本需求",
                supplement="",
                repos=[],
                settings=settings,
                defer_lark_resolution=True,
            )

            self.assertEqual(status, "input_ready")
            task_dir = settings.task_root / task_id
            self.assertTrue((task_dir / "prd.source.md").exists())

    def test_create_text_task_marks_input_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            task_id, status = create_task(
                raw_input="需求原文第一段\n\n需求原文第二段",
                title="统一规则口径",
                supplement="补充说明一",
                repos=[],
                settings=settings,
                defer_lark_resolution=True,
            )

            self.assertEqual(status, "input_ready")
            task_dir = settings.task_root / task_id
            task_meta = json.loads((task_dir / "task.json").read_text())
            input_meta = json.loads((task_dir / "input.json").read_text())
            source_markdown = (task_dir / "prd.source.md").read_text()

            self.assertEqual(task_meta["status"], "input_ready")
            self.assertEqual(input_meta["supplement"], "补充说明一")
            self.assertIn("需求原文第一段", source_markdown)
            self.assertIn("## 研发补充说明", source_markdown)

    def test_create_lark_task_defers_input_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            task_id, status = create_task(
                raw_input="https://example.feishu.cn/wiki/abc123",
                title="飞书需求",
                supplement="补充说明二",
                repos=[],
                settings=settings,
                defer_lark_resolution=True,
            )

            self.assertEqual(status, "input_processing")
            task_dir = settings.task_root / task_id
            task_meta = json.loads((task_dir / "task.json").read_text())
            self.assertEqual(task_meta["status"], "input_processing")
            self.assertTrue((task_dir / "input.log").exists())

    def test_input_task_fetches_lark_content_and_marks_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_id, status = create_task(
                raw_input="https://example.feishu.cn/wiki/abc123",
                title="",
                supplement="补充说明三",
                repos=[],
                settings=settings,
                defer_lark_resolution=True,
            )
            self.assertEqual(status, "input_processing")

            with (
                patch("coco_flow.engines.input.pipeline.resolve_lark_doc_token", return_value=("doc123", "飞书标题")),
                patch("coco_flow.engines.input.pipeline.fetch_lark_doc_markdown", return_value=("# 正文\n\n这里是 PRD。", "飞书标题")),
            ):
                result = input_task(task_id, settings=settings)

            self.assertEqual(result, "input_ready")
            task_dir = settings.task_root / task_id
            task_meta = json.loads((task_dir / "task.json").read_text())
            source_meta = json.loads((task_dir / "source.json").read_text())
            source_markdown = (task_dir / "prd.source.md").read_text()

            self.assertEqual(task_meta["status"], "input_ready")
            self.assertEqual(task_meta["title"], "飞书标题")
            self.assertEqual(source_meta["doc_token"], "doc123")
            self.assertIn("# 正文", source_markdown)


if __name__ == "__main__":
    unittest.main()
