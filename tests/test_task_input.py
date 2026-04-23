from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.engines.shared.manual_extract import MANUAL_EXTRACT_HEADING
from coco_flow.engines.input.sources import fetch_lark_doc_markdown
from coco_flow.engines.input.lark_markdown import normalize_lark_markdown
from coco_flow.services.tasks.edit import update_artifact
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
                supplement=build_manual_extract(),
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
            supplement = build_manual_extract(scope="统一规则口径", change_point="统一服务端字段与展示口径。")

            task_id, status = create_task(
                raw_input="需求原文第一段\n\n需求原文第二段",
                title="统一规则口径",
                supplement=supplement,
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
            self.assertEqual(input_meta["supplement"], supplement)
            self.assertIn("需求原文第一段", source_markdown)
            self.assertIn(MANUAL_EXTRACT_HEADING, source_markdown)

    def test_create_lark_task_defers_input_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            task_id, status = create_task(
                raw_input="https://example.feishu.cn/wiki/abc123",
                title="飞书需求",
                supplement=build_manual_extract(scope="飞书需求接入", change_point="按文档提炼服务端改动点。"),
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
                supplement=build_manual_extract(scope="飞书正文同步", change_point="拉取后进入 refine。"),
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

    def test_create_task_requires_manual_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            with self.assertRaisesRegex(ValueError, "人工提炼范围不能为空"):
                create_task(
                    raw_input="需求原文",
                    title="缺少人工提炼",
                    supplement="",
                    repos=[],
                    settings=settings,
                    defer_lark_resolution=True,
                )

    def test_create_task_rejects_unchanged_manual_extract_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))

            with self.assertRaisesRegex(ValueError, "人工提炼范围未填写完整"):
                create_task(
                    raw_input="需求原文",
                    title="模板未填写",
                    supplement=build_manual_extract_template_only(),
                    repos=[],
                    settings=settings,
                    defer_lark_resolution=True,
                )

    def test_update_prd_source_requires_valid_manual_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_id, _status = create_task(
                raw_input="需求原文",
                title="编辑原文",
                supplement=build_manual_extract(),
                repos=[],
                settings=settings,
                defer_lark_resolution=True,
            )

            with self.assertRaisesRegex(ValueError, "人工提炼范围不能为空"):
                update_artifact(
                    task_id,
                    "prd.source.md",
                    "# PRD Source\n\n---\n\n需求原文\n",
                    settings=settings,
                )


def build_manual_extract(scope: str = "统一服务端范围", change_point: str = "按状态切分并列出服务端改动点。") -> str:
    return (
        "## 本次范围\n"
        f"- {scope}\n\n"
        "## 人工提炼改动点\n"
        f"- {change_point}\n\n"
        "## 明确不做\n"
        "- 无\n\n"
        "## 前置条件 / 待确认项\n"
        "- 无"
    )


def build_manual_extract_template_only() -> str:
    return (
        "## 本次范围\n"
        "- [必填] 这次只做什么，先用一句话收敛范围。\n\n"
        "## 人工提炼改动点\n"
        "- [必填] 按“场景 / 状态 / 改动”逐条列出服务端改动点。\n\n"
        "## 明确不做\n"
        "- 如无可写：无\n\n"
        "## 前置条件 / 待确认项\n"
        "- 如有实验命中条件、接口依赖、跨端协同点，请写这里；如无可写：无"
    )


if __name__ == "__main__":
    unittest.main()
