from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coco_flow.clients import AgentSessionHandle
from coco_flow.config import Settings
from coco_flow.engines.refine.brief import build_refine_brief, merge_brief_with_refined_markdown, parse_manual_extract
from coco_flow.engines.refine.generate import _extract_markdown_section, _verify_with_local_repair, render_refined_markdown, verify_refine_output
from coco_flow.services.tasks.refine import refine_task, start_refining_task


def make_settings(root: Path, refine_executor: str = "local") -> Settings:
    config_root = root / "config"
    task_root = config_root / "tasks"
    task_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        config_root=config_root,
        task_root=task_root,
        refine_executor=refine_executor,
        plan_executor="local",
        code_executor="local",
        enable_go_test_verify=False,
        coco_bin="coco",
        native_query_timeout="90s",
        native_code_timeout="10m",
        acp_idle_timeout_seconds=600.0,
        daemon_idle_timeout_seconds=3600.0,
    )


class RefineTaskTest(unittest.TestCase):
    def test_parse_manual_extract_splits_gating_and_open_questions(self) -> None:
        manual = parse_manual_extract(
            "## 本次范围\n"
            "- 只处理服务端文案实验范围。\n\n"
            "## 人工提炼改动点\n"
            "- 普通竞拍预热态展示 Starting bid。\n\n"
            "## 明确不做\n"
            "- 不改横滑交互。\n\n"
            "## 前置条件 / 待确认项\n"
            "- 命中第一个实验。\n"
            "- 是否需要兼容老 key？\n"
        )

        self.assertEqual(manual.scope, ["只处理服务端文案实验范围。"])
        self.assertEqual(manual.change_points, ["普通竞拍预热态展示 Starting bid。"])
        self.assertEqual(manual.out_of_scope, ["不改横滑交互。"])
        self.assertEqual(manual.gating_conditions, ["命中第一个实验。"])
        self.assertEqual(manual.open_questions, ["是否需要兼容老 key？"])

    def test_parse_manual_extract_keeps_leaf_change_points(self) -> None:
        manual = parse_manual_extract(
            "## 本次范围\n"
            "- 只改竞拍讲解卡文案。\n\n"
            "## 人工提炼改动点\n"
            "命中第一个实验， 会改动以下：\n\n"
            "1. 普通竞拍 / Temporary listing\n"
            "   - 预热态：{起拍价} + Starting bid\n"
            "   - 竞拍中：\n"
            "     - 无人出价：{起拍价} + 轮播 Starting bid / Bid first\n"
            "2. surprise set\n"
            "   - 预热态：{起拍价} + Starting bid\n"
            "   - 竞拍中：\n"
            "     - 无人出价：{当前最高价} + 轮播 Starting bid / Bid first to unlock a surprise!\n"
        )

        self.assertEqual(manual.gating_conditions, ["命中第一个实验"])
        self.assertEqual(
            manual.change_points,
            [
                "普通竞拍 / Temporary listing / 预热态：{起拍价} + Starting bid",
                "普通竞拍 / Temporary listing / 竞拍中 / 无人出价：{起拍价} + 轮播 Starting bid / Bid first",
                "surprise set / 预热态：{起拍价} + Starting bid",
                "surprise set / 竞拍中 / 无人出价：{当前最高价} + 轮播 Starting bid / Bid first to unlock a surprise!",
            ],
        )

    def test_build_refine_brief_keeps_manual_extract_as_primary_source(self) -> None:
        manual = parse_manual_extract(
            "## 本次范围\n"
            "- 只处理服务端文案实验范围。\n\n"
            "## 人工提炼改动点\n"
            "- 普通竞拍预热态：{起拍价} + Starting bid。\n"
            "- 普通竞拍无人出价态：{起拍价} + 轮播 Starting bid / Bid first。\n\n"
            "## 明确不做\n"
            "- 不改横滑和震感。\n\n"
            "## 前置条件 / 待确认项\n"
            "- 命中第一个实验。\n"
        )
        prepared = type(
            "Prepared",
            (),
            {
                "title": "竞拍讲解卡爽感增强",
                "supplement": "",
                "source_content": "PRD 里还有横滑和震感描述。",
            },
        )()

        brief = build_refine_brief(prepared, manual)

        self.assertEqual(brief.target_surface, "backend")
        self.assertEqual(brief.goal, "只处理服务端文案实验范围。")
        self.assertEqual(len(brief.in_scope), 2)
        self.assertIn("命中第一个实验。", brief.gating_conditions)
        self.assertIn("不改横滑和震感。", brief.out_of_scope)
        self.assertEqual(len(brief.acceptance_criteria), 2)

    def test_render_refined_markdown_writes_gating_condition_in_change_scope(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡爽感增强",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只处理服务端文案实验范围。\n\n"
                "## 人工提炼改动点\n"
                "命中第一个实验， 会改动以下：\n"
                "- 普通竞拍预热态：{起拍价} + Starting bid。\n"
            ),
        )

        refined = render_refined_markdown(brief)

        change_section = _extract_markdown_section(refined, "具体变更点")
        self.assertIn("适用条件：命中第一个实验", change_section)
        self.assertIn("普通竞拍预热态", change_section)

    def test_render_refined_markdown_uses_grouped_table_for_path_changes(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡文案",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只改竞拍讲解卡文案。\n\n"
                "## 人工提炼改动点\n"
                "命中第一个实验， 会改动以下：\n"
                "1. 普通竞拍 / Temporary listing\n"
                "   - 预热态：{起拍价} + Starting bid\n"
                "   - 竞拍中：\n"
                "     - 无人出价：{起拍价} + 轮播 Starting bid / Bid first\n"
                "2. surprise set\n"
                "   - 预热态：{起拍价} + Starting bid\n"
                "   - 竞拍中：\n"
                "     - 无人出价：{当前最高价} + 轮播 Starting bid / Bid first to unlock a surprise!\n"
            ),
        )

        refined = render_refined_markdown(brief)
        verify = verify_refine_output(brief, refined)

        change_section = _extract_markdown_section(refined, "具体变更点")
        acceptance_section = _extract_markdown_section(refined, "验收标准")
        self.assertIn("### 普通竞拍 / Temporary listing", change_section)
        self.assertIn("| 状态 | 展示内容 |", change_section)
        self.assertIn("| 竞拍中 / 无人出价 | {起拍价} + 轮播 Starting bid / Bid first |", change_section)
        self.assertIn("### surprise set", change_section)
        self.assertNotIn("### surprise set / 竞拍中", change_section)
        self.assertIn("| 竞拍中 / 无人出价 | {当前最高价} + 轮播 Starting bid / Bid first to unlock a surprise! |", change_section)
        self.assertIn("命中第一个实验时，普通竞拍 / Temporary listing 的预热态、竞拍中 / 无人出价按上表展示。", acceptance_section)
        self.assertIn("命中第一个实验时，surprise set 的预热态、竞拍中 / 无人出价按上表展示。", acceptance_section)
        self.assertTrue(verify.ok, verify.issues)

    def test_render_refined_markdown_keeps_bullets_for_non_path_changes(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡爽感增强",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只处理服务端文案实验范围。\n\n"
                "## 人工提炼改动点\n"
                "命中第一个实验， 会改动以下：\n"
                "- 明确竞拍态展示条件，并确认非竞拍态是否不展示。\n"
            ),
        )

        refined = render_refined_markdown(brief)

        change_section = _extract_markdown_section(refined, "具体变更点")
        self.assertIn("- 适用条件：命中第一个实验", change_section)
        self.assertIn("- 明确竞拍态展示条件，并确认非竞拍态是否不展示。", change_section)
        self.assertNotIn("| 状态 | 展示内容 |", change_section)

    def test_merge_brief_with_refined_markdown_syncs_agent_added_boundary(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡爽感增强",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只处理服务端文案实验范围。\n\n"
                "## 人工提炼改动点\n"
                "- 普通竞拍预热态：{起拍价} + Starting bid。\n\n"
                "## 明确不做\n"
                "- 不改横滑和震感。\n\n"
                "## 前置条件 / 待确认项\n"
                "- 命中第一个实验。\n"
            ),
        )
        merged = merge_brief_with_refined_markdown(
            brief,
            (
                "# 需求确认书\n\n"
                "## 需求概述\nA\n\n"
                "## 具体变更点\n- 适用条件：命中第一个实验。\n- 普通竞拍预热态：{起拍价} + Starting bid。\n\n"
                "## 验收标准\n- 当命中第一个实验时，普通竞拍预热态正确生效。\n\n"
                "## 边界与非目标\n- 不改横滑和震感。\n- 购物袋商卡和Maxbid面板卡片先不改。\n\n"
                "## 待确认项\n- 无\n"
            ),
        )

        self.assertIn("购物袋商卡和Maxbid面板卡片先不改。", merged.out_of_scope)
        self.assertEqual(merged.in_scope, ["普通竞拍预热态：{起拍价} + Starting bid。"])

    def test_verify_rejects_gating_condition_only_in_acceptance(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡爽感增强",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只处理服务端文案实验范围。\n\n"
                "## 人工提炼改动点\n"
                "命中第一个实验， 会改动以下：\n"
                "- 普通竞拍预热态：{起拍价} + Starting bid。\n"
            ),
        )

        verify = verify_refine_output(
            brief,
            (
                "# 需求确认书\n\n"
                "## 需求概述\nA\n\n"
                "## 具体变更点\n- 普通竞拍预热态：{起拍价} + Starting bid。\n\n"
                "## 验收标准\n- 当命中第一个实验时，普通竞拍预热态正确生效。\n\n"
                "## 边界与非目标\n- 不扩大到人工提炼范围之外的 UI、动效、交互或相邻系统改动。\n\n"
                "## 待确认项\n- 无\n"
            ),
        )

        self.assertFalse(verify.ok)
        self.assertIn("具体变更点缺少适用条件：命中第一个实验", verify.issues)
        self.assertEqual(verify.failure_type, "missing_gating_condition")


    def test_verify_rejects_boundary_sentence_inside_acceptance(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡爽感增强",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只处理服务端文案实验范围。\n\n"
                "## 人工提炼改动点\n"
                "- 普通竞拍预热态：{起拍价} + Starting bid。\n\n"
                "## 明确不做\n"
                "- 不改横滑和震感。\n\n"
                "## 前置条件 / 待确认项\n"
                "- 命中第一个实验。\n"
            ),
        )
        verify = verify_refine_output(
            brief,
            (
                "# 需求确认书\n\n"
                "## 需求概述\nA\n\n"
                "## 具体变更点\n- X\n\n"
                "## 验收标准\n- 未纳入范围的内容保持不变。\n\n"
                "## 边界与非目标\n- Y\n\n"
                "## 待确认项\n- Z\n"
            ),
        )

        self.assertFalse(verify.ok)
        self.assertIn("验收标准混入了边界说明。", verify.issues)
        self.assertEqual(verify.failure_type, "acceptance_boundary_mixed")

    def test_refine_local_repair_fixes_low_risk_markdown_issues(self) -> None:
        brief = build_refine_brief(
            type(
                "Prepared",
                (),
                {
                    "title": "竞拍讲解卡爽感增强",
                    "supplement": "",
                    "source_content": "",
                },
            )(),
            parse_manual_extract(
                "## 本次范围\n"
                "- 只处理服务端文案实验范围。\n\n"
                "## 人工提炼改动点\n"
                "- 普通竞拍预热态：{起拍价} + Starting bid。\n\n"
                "## 明确不做\n"
                "- 不改横滑和震感。\n\n"
                "## 前置条件 / 待确认项\n"
                "- 命中第一个实验。\n"
            ),
        )
        broken = (
            "# 需求确认书\n\n"
            "## 需求概述\n- 待补充\n\n"
            "## 具体变更点\n- 普通竞拍预热态：{起拍价} + Starting bid。\n\n"
            "## 验收标准\n"
            "- 当命中第一个实验时，普通竞拍预热态：{起拍价} + Starting bid。正确生效。\n"
            "- 未纳入范围的内容保持不变。\n\n"
            "## 边界与非目标\n- 不改横滑和震感。\n"
        )
        logs: list[str] = []

        repaired, verify = _verify_with_local_repair(brief, broken, logs.append)

        self.assertTrue(verify.ok)
        self.assertEqual(verify.repair_attempts, 1)
        self.assertIn("## 待确认项", repaired)
        self.assertIn("适用条件：命中第一个实验", _extract_markdown_section(repaired, "具体变更点"))
        self.assertNotIn("待补充", repaired)
        self.assertNotIn("未纳入范围", _extract_markdown_section(repaired, "验收标准"))
        self.assertTrue(any("refine_repair_attempt: 1" in line for line in logs))

    def test_start_refining_task_requires_manual_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_dir = build_task(
                settings=settings,
                task_id="task-missing-manual-extract",
                title="缺少人工提炼范围",
                source_markdown="# PRD Source\n\n---\n\n只有原始 PRD，没有人工提炼范围。\n",
                supplement="",
            )
            input_meta = json.loads((task_dir / "input.json").read_text(encoding="utf-8"))
            input_meta["supplement"] = ""
            (task_dir / "input.json").write_text(json.dumps(input_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "人工提炼范围不能为空"):
                start_refining_task("task-missing-manual-extract", settings=settings)
            diagnosis = json.loads((task_dir / "refine-diagnosis.json").read_text(encoding="utf-8"))
            self.assertEqual(diagnosis["severity"], "needs_human")
            self.assertEqual(diagnosis["failure_type"], "missing_human_scope")
            self.assertEqual(diagnosis["next_action"], "needs_human")
            self.assertFalse(diagnosis["retryable"])
            self.assertEqual(diagnosis["missing_sections"], ["本次范围", "人工提炼改动点"])

    def test_start_refining_task_writes_needs_human_for_incomplete_manual_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_dir = build_task(
                settings=settings,
                task_id="task-incomplete-manual-extract",
                title="缺少改动点",
                source_markdown="# PRD Source\n\n---\n\n只有原始 PRD。\n",
                supplement=(
                    "## 本次范围\n"
                    "- 只处理服务端文案实验范围。\n\n"
                    "## 人工提炼改动点\n"
                    "- [必填] 按“场景 / 状态 / 改动”逐条列出服务端改动点。\n\n"
                    "## 明确不做\n"
                    "- 无\n\n"
                    "## 前置条件 / 待确认项\n"
                    "- 无\n"
                ),
            )

            with self.assertRaisesRegex(ValueError, "人工提炼范围未填写完整"):
                start_refining_task("task-incomplete-manual-extract", settings=settings)
            diagnosis = json.loads((task_dir / "refine-diagnosis.json").read_text(encoding="utf-8"))
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))

            self.assertEqual(diagnosis["severity"], "needs_human")
            self.assertEqual(diagnosis["missing_sections"], ["人工提炼改动点"])
            self.assertEqual(diagnosis["issues"][0]["path"], "人工提炼范围.人工提炼改动点")
            self.assertFalse(diagnosis["issues"][0]["auto_repairable"])
            self.assertEqual(verify["next_action"], "needs_human")

    def test_local_refine_writes_new_brief_and_verify_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            task_dir = build_task(
                settings=settings,
                task_id="task-local",
                title="竞拍讲解卡增加竞拍态提示",
                source_markdown=(
                    "# PRD Source\n\n"
                    "- title: 竞拍讲解卡增加竞拍态提示\n"
                    "- source_type: text\n\n"
                    "---\n\n"
                    "竞拍讲解卡需要展示竞拍态提示。\n"
                    "需要确认非竞拍态是否展示。\n"
                ),
                supplement=build_manual_extract(),
            )

            status = refine_task("task-local", settings=settings)

            self.assertEqual(status, "refined")
            refined = (task_dir / "prd-refined.md").read_text(encoding="utf-8")
            brief = json.loads((task_dir / "refine-brief.json").read_text(encoding="utf-8"))
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))
            diagnosis = json.loads((task_dir / "refine-diagnosis.json").read_text(encoding="utf-8"))
            compat_intent = json.loads((task_dir / "refine-intent.json").read_text(encoding="utf-8"))

            self.assertIn("# 需求确认书", refined)
            self.assertIn("## 具体变更点", refined)
            self.assertEqual(brief["target_surface"], "backend")
            self.assertTrue(brief["in_scope"])
            self.assertTrue(verify["ok"])
            self.assertEqual(verify["stage"], "refine")
            self.assertEqual(verify["next_action"], "continue")
            self.assertEqual(diagnosis["stage"], "refine")
            self.assertTrue(diagnosis["ok"])
            self.assertEqual(compat_intent["mode"], "manual_first")
            self.assertEqual(compat_intent["change_points"], brief["in_scope"])

    def test_native_refine_now_uses_same_manual_first_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            task_dir = build_task(
                settings=settings,
                task_id="task-native",
                title="竞拍讲解卡增加竞拍态提示",
                source_markdown="# PRD Source\n\n---\n\n竞拍讲解卡需要展示竞拍态提示。\n",
                supplement=build_manual_extract(),
            )
            session_roles: list[str] = []
            prompt_roles: list[str] = []
            with (
                patch(
                    "coco_flow.engines.refine.generate.CocoACPClient.new_agent_session",
                    side_effect=lambda *, query_timeout, cwd, role: make_agent_session_handle(
                        query_timeout=query_timeout,
                        cwd=cwd,
                        role=role,
                        roles=session_roles,
                    ),
                ),
                patch(
                    "coco_flow.engines.refine.generate.CocoACPClient.prompt_agent_session",
                    side_effect=lambda handle, prompt: write_native_refine_artifacts(handle, prompt, prompt_roles),
                ),
                patch("coco_flow.engines.refine.generate.CocoACPClient.close_agent_session") as close_session,
            ):
                status = refine_task("task-native", settings=settings)

            self.assertEqual(status, "refined")
            brief = json.loads((task_dir / "refine-brief.json").read_text(encoding="utf-8"))
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))
            diagnosis = json.loads((task_dir / "refine-diagnosis.json").read_text(encoding="utf-8"))
            refined = (task_dir / "prd-refined.md").read_text(encoding="utf-8")
            refine_log = (task_dir / "refine.log").read_text(encoding="utf-8")
            self.assertEqual(brief["target_surface"], "backend")
            self.assertTrue(verify["ok"])
            self.assertEqual(diagnosis["next_action"], "continue")
            self.assertIn("当命中第一个实验", refined)
            self.assertIn("购物袋商卡和Maxbid面板卡片先不改。", brief["out_of_scope"])
            self.assertFalse((task_dir / "refine-skills-selection.json").exists())
            self.assertEqual(session_roles, ["refine_generate", "refine_verify"])
            self.assertEqual(prompt_roles, ["refine_generate", "refine_generate", "refine_verify"])
            self.assertEqual(close_session.call_count, 2)
            self.assertIn("generate_mode: agent_session", refine_log)
            self.assertIn("session_role: refine_generate", refine_log)
            self.assertIn("session_role: refine_verify", refine_log)
            self.assertIn("bootstrap_prompt: true role=refine_generate", refine_log)
            self.assertIn("bootstrap_prompt: inline role=refine_verify", refine_log)

    def test_native_refine_repairs_agent_bullet_output_back_to_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), refine_executor="native")
            task_dir = build_task(
                settings=settings,
                task_id="task-native-table",
                title="竞拍讲解卡文案",
                source_markdown="# PRD Source\n\n---\n\n竞拍讲解卡需要展示文案。\n",
                supplement=(
                    "## 本次范围\n"
                    "- 只改竞拍讲解卡文案。\n\n"
                    "## 人工提炼改动点\n"
                    "命中第一个实验， 会改动以下：\n"
                    "1. 普通竞拍 / Temporary listing\n"
                    "   - 预热态：{起拍价} + Starting bid\n"
                    "   - 竞拍中：\n"
                    "     - 无人出价：{起拍价} + 轮播 Starting bid / Bid first\n"
                    "2. surprise set\n"
                    "   - 预热态：{起拍价} + Starting bid\n"
                    "   - 竞拍中：\n"
                    "     - 无人出价：{当前最高价} + 轮播 Starting bid / Bid first to unlock a surprise!\n"
                ),
            )
            session_roles: list[str] = []
            prompt_roles: list[str] = []
            with (
                patch(
                    "coco_flow.engines.refine.generate.CocoACPClient.new_agent_session",
                    side_effect=lambda *, query_timeout, cwd, role: make_agent_session_handle(
                        query_timeout=query_timeout,
                        cwd=cwd,
                        role=role,
                        roles=session_roles,
                    ),
                ),
                patch(
                    "coco_flow.engines.refine.generate.CocoACPClient.prompt_agent_session",
                    side_effect=lambda handle, prompt: write_native_refine_bullet_artifacts(handle, prompt, prompt_roles),
                ),
                patch("coco_flow.engines.refine.generate.CocoACPClient.close_agent_session"),
            ):
                status = refine_task("task-native-table", settings=settings)

            refined = (task_dir / "prd-refined.md").read_text(encoding="utf-8")
            verify = json.loads((task_dir / "refine-verify.json").read_text(encoding="utf-8"))

            self.assertEqual(status, "refined")
            self.assertTrue(verify["ok"])
            self.assertEqual(verify["repair_attempts"], 1)
            self.assertIn("| 状态 | 展示内容 |", refined)
            self.assertIn("### 普通竞拍 / Temporary listing", refined)
            self.assertIn("命中第一个实验时，surprise set 的预热态、竞拍中 / 无人出价按上表展示。", refined)
            self.assertEqual(session_roles, ["refine_generate", "refine_verify"])
            self.assertEqual(prompt_roles, ["refine_generate", "refine_generate", "refine_verify"])


def build_task(*, settings: Settings, task_id: str, title: str, source_markdown: str, supplement: str | None = None) -> Path:
    task_dir = settings.task_root / task_id
    task_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    normalized_supplement = supplement if supplement is not None else build_manual_extract()
    has_manual_extract = "## 人工提炼范围" in source_markdown or "## 研发补充说明" in source_markdown
    final_source_markdown = (
        source_markdown
        if has_manual_extract
        else source_markdown.rstrip() + f"\n\n## 人工提炼范围\n\n{normalized_supplement}\n"
    )
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "title": title,
                "status": "input_ready",
                "created_at": now,
                "updated_at": now,
                "source_type": "text",
                "source_value": title,
                "repo_count": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "repos.json").write_text(json.dumps({"repos": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (task_dir / "input.json").write_text(
        json.dumps(
            {
                "title": title,
                "title_explicit": True,
                "source_input": title,
                "supplement": normalized_supplement,
                "source_type": "text",
                "status": "input_ready",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "source.json").write_text(
        json.dumps({"type": "text", "title": title}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_dir / "prd.source.md").write_text(final_source_markdown, encoding="utf-8")
    return task_dir


def build_manual_extract() -> str:
    return (
        "## 本次范围\n"
        "- 只处理竞拍讲解卡服务端展示口径。\n\n"
        "## 人工提炼改动点\n"
        "- 明确竞拍态展示条件，并确认非竞拍态是否不展示。\n\n"
        "## 明确不做\n"
        "- 不改横滑和震感。\n\n"
        "## 前置条件 / 待确认项\n"
        "- 命中第一个实验。\n"
        "- 是否需要兼容旧 key？\n"
    )


if __name__ == "__main__":
    unittest.main()


def make_agent_session_handle(*, query_timeout: str, cwd: str, role: str, roles: list[str]) -> AgentSessionHandle:
    roles.append(role)
    return AgentSessionHandle(
        handle_id=f"{role}-handle",
        cwd=cwd,
        mode="agent",
        query_timeout=query_timeout,
        role=role,
    )


def write_native_refine_artifacts(handle: AgentSessionHandle, prompt: str, prompt_roles: list[str]) -> str:
    task_dir = Path(handle.cwd)
    prompt_roles.append(handle.role)
    if handle.role == "refine_generate" and "收到 bootstrap 后只需简短回复已完成" in prompt:
        return "done"
    if handle.role == "refine_verify" and list(task_dir.glob(".refine-verify-*.json")):
        next(task_dir.glob(".refine-verify-*.json")).write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "missing_sections": [],
                    "reason": "agent verify passed",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return "done"
    if handle.role == "refine_generate" and list(task_dir.glob(".refine-template-*.md")):
        next(task_dir.glob(".refine-template-*.md")).write_text(
            (
                "# 需求确认书\n\n"
                "## 需求概述\n"
                "只处理竞拍讲解卡服务端展示口径。\n\n"
                "## 具体变更点\n"
                "- 明确竞拍态展示条件，并确认非竞拍态是否不展示。\n\n"
                "## 验收标准\n"
                "- 当命中第一个实验时，明确定义的竞拍态展示条件正确生效。\n\n"
                "## 边界与非目标\n"
                "- 不改横滑和震感。\n"
                "- 购物袋商卡和Maxbid面板卡片先不改。\n\n"
                "## 待确认项\n"
                "- 是否需要兼容旧 key？\n"
            ),
            encoding="utf-8",
        )
        return "done"
    raise AssertionError(f"unexpected refine agent prompt: {prompt[:120]}")


def write_native_refine_bullet_artifacts(handle: AgentSessionHandle, prompt: str, prompt_roles: list[str]) -> str:
    task_dir = Path(handle.cwd)
    prompt_roles.append(handle.role)
    if handle.role == "refine_generate" and "收到 bootstrap 后只需简短回复已完成" in prompt:
        return "done"
    if handle.role == "refine_verify" and list(task_dir.glob(".refine-verify-*.json")):
        next(task_dir.glob(".refine-verify-*.json")).write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "missing_sections": [],
                    "reason": "agent verify passed",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return "done"
    if handle.role == "refine_generate" and list(task_dir.glob(".refine-template-*.md")):
        next(task_dir.glob(".refine-template-*.md")).write_text(
            (
                "# 需求确认书\n\n"
                "## 需求概述\n"
                "只改竞拍讲解卡文案。\n\n"
                "## 具体变更点\n"
                "适用条件：命中第一个实验\n"
                "- 普通竞拍 / Temporary listing / 预热态：{起拍价} + Starting bid\n"
                "- 普通竞拍 / Temporary listing / 竞拍中 / 无人出价：{起拍价} + 轮播 Starting bid / Bid first\n"
                "- surprise set / 预热态：{起拍价} + Starting bid\n"
                "- surprise set / 竞拍中 / 无人出价：{当前最高价} + 轮播 Starting bid / Bid first to unlock a surprise!\n\n"
                "## 验收标准\n"
                "- 当命中第一个实验时，普通竞拍 / Temporary listing / 预热态应该正确显示 {起拍价} + Starting bid。\n"
                "- 当命中第一个实验且 surprise set 竞拍中无人出价时，应该正确显示文案。\n\n"
                "## 边界与非目标\n"
                "- 不扩大到人工提炼范围之外的 UI、动效、交互或相邻系统改动。\n\n"
                "## 待确认项\n"
                "- 无\n"
            ),
            encoding="utf-8",
        )
        return "done"
    raise AssertionError(f"unexpected refine agent prompt: {prompt[:120]}")
