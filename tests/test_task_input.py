from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.engines.input.sources import fetch_lark_doc_markdown
from coco_flow.engines.input.lark_markdown import normalize_lark_markdown
from coco_flow.services.tasks.input import create_task, input_task


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


class InputTaskTest(unittest.TestCase):
    def test_normalize_lark_markdown_flattens_rich_tags(self) -> None:
        raw = """
# Version Control

<lark-table rows="2" cols="2">
  <lark-tr>
    <lark-td>**Key**</lark-td>
    <lark-td>**Value**</lark-td>
  </lark-tr>
  <lark-tr>
    <lark-td>Owner</lark-td>
    <lark-td><mention-user id="ou_demo"/></lark-td>
  </lark-tr>
</lark-table>

<callout emoji="dart">
# Summary

强化爽感
</callout>

<quote-container>
<mention-doc token="wiki123" type="wiki">相关文档</mention-doc>
</quote-container>
"""

        normalized = normalize_lark_markdown(raw)

        self.assertIn("| **Key** | **Value** |", normalized)
        self.assertIn("| Owner | @ou_demo |", normalized)
        self.assertIn("# Summary", normalized)
        self.assertIn("强化爽感", normalized)
        self.assertIn("[相关文档](https://bytedance.larkoffice.com/wiki/wiki123)", normalized)

    def test_normalize_lark_markdown_removes_dangling_heading_markers(self) -> None:
        raw = """
<lark-table rows="2" cols="1">
  <lark-tr>
    <lark-td>Title</lark-td>
  </lark-tr>
  <lark-tr>
    <lark-td>
      #### **普通竞拍 / Temporary listing**
      ####
    </lark-td>
  </lark-tr>
</lark-table>
"""

        normalized = normalize_lark_markdown(raw)

        self.assertIn("| #### **普通竞拍 / Temporary listing** |", normalized)
        self.assertNotIn("listing**####", normalized)
        self.assertNotIn("| #### |", normalized)

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

    def test_fetch_lark_doc_markdown_normalizes_rich_markdown(self) -> None:
        raw_markdown = """
# Links

<lark-table rows="2" cols="2">
  <lark-tr>
    <lark-td>**Name**</lark-td>
    <lark-td>**Doc**</lark-td>
  </lark-tr>
  <lark-tr>
    <lark-td>参考</lark-td>
    <lark-td><mention-doc token="abc" type="wiki">设计稿</mention-doc></lark-td>
  </lark-tr>
</lark-table>
"""
        payload = {
            "ok": True,
            "data": {
                "title": "飞书标题",
                "markdown": raw_markdown,
            },
        }

        with (
            patch("coco_flow.engines.input.sources.ensure_lark_cli"),
            patch(
                "coco_flow.engines.input.sources.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload, ensure_ascii=False), stderr=""),
            ),
        ):
            markdown, title = fetch_lark_doc_markdown("doc123")

        self.assertEqual(title, "飞书标题")
        self.assertIn("| **Name** | **Doc** |", markdown)
        self.assertIn("[设计稿](https://bytedance.larkoffice.com/wiki/abc)", markdown)


if __name__ == "__main__":
    unittest.main()
