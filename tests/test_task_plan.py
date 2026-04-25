from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coco_flow.clients import AgentSessionHandle
from coco_flow.config import Settings
from coco_flow.engines.plan.pipeline import run_plan_engine
from coco_flow.engines.shared.models import (
    ContextSnapshot,
    RefinedSections,
    RepoResearch,
    ResearchFinding,
)
from coco_flow.engines.shared.research import build_design_research_signals, parse_refined_sections
from coco_flow.services.tasks.edit import update_artifact
from coco_flow.services.tasks.plan import plan_task


class PlanTaskBuilderTest(unittest.TestCase):
    def test_local_plan_generates_doc_only_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root)
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")

            result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, lambda _line: None)

            self.assertEqual(result.status, "planned")
            self.assertIn("# Plan", result.plan_markdown)
            self.assertIn("## 任务清单", result.plan_markdown)
            self.assertIn("## 执行顺序", result.plan_markdown)
            self.assertIn("depends_on", result.plan_markdown)
            self.assertTrue(result.plan_work_items_payload.get("work_items"))
            self.assertTrue(result.plan_validation_payload.get("task_validations"))

    def test_native_plan_falls_back_to_local_doc_only_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root, plan_executor="native")
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")

            with patch(
                "coco_flow.engines.plan.agent_io.CocoACPClient.new_agent_session",
                side_effect=ValueError("plan native unavailable"),
            ):
                result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, lambda _line: None)

            self.assertEqual(result.status, "planned")
            self.assertIn("# Plan", result.plan_markdown)
            self.assertIn("## 验证策略", result.plan_markdown)
            self.assertIn("depends_on", result.plan_markdown)
            self.assertTrue(result.plan_work_items_payload.get("work_items"))

    def test_native_plan_uses_single_writer_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root, plan_executor="native")
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")
            logs: list[str] = []
            roles: list[str] = []
            prompts: list[str] = []
            closed_roles: list[str] = []

            def fake_new_session(*, query_timeout: str, cwd: str, role: str) -> AgentSessionHandle:
                roles.append(role)
                return AgentSessionHandle(
                    handle_id=f"handle-{role}",
                    cwd=cwd,
                    mode="agent",
                    query_timeout=query_timeout,
                    role=role,
                )

            def fake_prompt_session(handle: AgentSessionHandle, prompt: str) -> str:
                prompts.append(prompt)
                _write_plan_native_template(prompt)
                return "ok"

            def fake_close_session(handle: AgentSessionHandle) -> None:
                closed_roles.append(handle.role)

            with (
                patch("coco_flow.engines.plan.agent_io.CocoACPClient.new_agent_session", side_effect=fake_new_session),
                patch("coco_flow.engines.plan.agent_io.CocoACPClient.prompt_agent_session", side_effect=fake_prompt_session),
                patch("coco_flow.engines.plan.agent_io.CocoACPClient.close_agent_session", side_effect=fake_close_session),
            ):
                result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, logs.append)

            self.assertEqual(result.status, "planned")
            self.assertEqual(roles, ["plan_writer"])
            self.assertEqual(closed_roles, ["plan_writer"])
            self.assertEqual(len(prompts), 1)
            self.assertIn("这是内联 bootstrap", prompts[0])
            self.assertIn("session_role: plan_writer", logs)
            self.assertIn("bootstrap_prompt: inline role=plan_writer", logs)

    def test_plan_engine_builds_cross_repo_dependency_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root)
            task_dir = self._create_cross_repo_plan_ready_task(settings.task_root, root)

            result = run_plan_engine(task_dir, {"title": "竞拍讲解卡文案"}, settings, lambda _line: None)

            edges = result.plan_execution_graph_payload.get("edges")
            self.assertIsInstance(edges, list)
            self.assertEqual(len(edges), 1)
            edge = edges[0]
            self.assertEqual(edge["type"], "hard_dependency")
            self.assertIn("W1", result.plan_markdown)
            self.assertIn("W2", result.plan_markdown)
            self.assertIn("code_allowed: false", result.plan_markdown)
            self.assertFalse(result.plan_result_payload.get("code_allowed"))
            self.assertTrue(result.repo_task_markdowns.get("live_common"))
            self.assertTrue(result.repo_task_markdowns.get("live_pack"))

    def test_plan_task_persists_structured_sidecars_and_repo_markdowns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root)
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")
            self._write_json(task_dir / "task.json", {"task_id": "task-plan", "title": "直播列表国家筛选", "status": "designed"})

            status = plan_task("task-plan", settings=settings, on_log=lambda _line: None)

            self.assertEqual(status, "planned")
            self.assertTrue((task_dir / "plan-work-items.json").exists())
            self.assertTrue((task_dir / "plan-execution-graph.json").exists())
            self.assertTrue((task_dir / "plan-validation.json").exists())
            self.assertTrue((task_dir / "plan-result.json").exists())
            self.assertTrue((task_dir / "plan-repos" / "live-api.md").exists())
            repo_plan = (task_dir / "plan-repos" / "live-api.md").read_text(encoding="utf-8")
            self.assertNotIn("done_definition", repo_plan)
            self.assertNotIn("验收映射", repo_plan)
            self.assertNotIn("## 验证", repo_plan)

    def test_repo_plan_markdown_can_be_edited_after_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root)
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")
            self._write_json(task_dir / "task.json", {"task_id": "task-plan", "title": "直播列表国家筛选", "status": "designed"})

            plan_task("task-plan", settings=settings, on_log=lambda _line: None)
            status, content = update_artifact("task-plan", "plan.md", "# live-api Plan\n\n- 人工调整。\n", settings=settings, repo_id="live-api")

            self.assertEqual(status, "planned")
            self.assertIn("人工调整", content)
            self.assertIn("人工调整", (task_dir / "plan-repos" / "live-api.md").read_text(encoding="utf-8"))

    def test_build_design_research_signals_extracts_specialized_hints(self) -> None:
        sections = RefinedSections(
            change_scope=["补齐多端状态提示链路"],
            non_goals=["不改旧样式"],
            key_constraints=["保持接口兼容", "配置默认关闭"],
            acceptance_criteria=["状态提示展示正确"],
            open_questions=["是否需要实验灰度"],
            raw="",
        )
        repo_researches = [
            RepoResearch(
                repo_id="live-api",
                repo_path="/tmp/live-api",
                context=ContextSnapshot(available=False),
                finding=ResearchFinding(
                    matched_terms=[],
                    unmatched_terms=[],
                    candidate_files=[
                        "idl/live_status.thrift",
                        "config/live_status_switch.go",
                        "service/experiment_bucket.go",
                    ],
                    candidate_dirs=["idl", "config", "service"],
                    notes=["存在跨模块联动"],
                ),
            )
        ]

        signals = build_design_research_signals(repo_researches, sections)

        self.assertTrue(signals.system_summaries)
        self.assertTrue(signals.system_dependencies)
        self.assertTrue(signals.critical_flows)
        self.assertTrue(signals.interface_changes)
        self.assertTrue(signals.risk_boundaries)

    def test_parse_refined_sections_supports_new_titles(self) -> None:
        sections = parse_refined_sections(
            "# PRD Refined\n\n"
            "## 变更范围\n\n"
            "- 支持直播列表按国家筛选。\n\n"
            "## 非目标\n\n"
            "- 不改接口协议。\n\n"
            "## 关键约束\n\n"
            "- 保持原有排序。\n\n"
            "## 验收标准\n\n"
            "- 国家筛选结果正确。\n\n"
            "## 待确认项\n\n"
            "- 是否需要兼容旧筛选入口。\n"
        )

        self.assertEqual(sections.change_scope, ["支持直播列表按国家筛选。"])
        self.assertEqual(sections.non_goals, ["不改接口协议。"])
        self.assertEqual(sections.key_constraints, ["保持原有排序。"])
        self.assertEqual(sections.acceptance_criteria, ["国家筛选结果正确。"])
        self.assertEqual(sections.open_questions, ["是否需要兼容旧筛选入口。"])

    def _settings(self, root: Path, *, plan_executor: str = "local") -> Settings:
        config_root = root / "config"
        task_root = config_root / "tasks"
        task_root.mkdir(parents=True, exist_ok=True)
        return Settings(
            config_root=config_root,
            task_root=task_root,
            refine_executor="local",
            plan_executor=plan_executor,
            code_executor="local",
            enable_go_test_verify=False,
            coco_bin="coco",
            native_query_timeout="90s",
            native_code_timeout="10m",
            acp_idle_timeout_seconds=600.0,
            daemon_idle_timeout_seconds=3600.0,
        )

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        import json

        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _create_plan_ready_task(self, task_root: Path, repo_dir: Path) -> Path:
        task_dir = task_root / "task-plan"
        task_dir.mkdir(parents=True)
        repo_dir.mkdir(parents=True)
        self._write_json(task_dir / "input.json", {"title": "直播列表国家筛选"})
        self._write_json(
            task_dir / "repos.json",
            {"repos": [{"id": "live-api", "path": str(repo_dir), "status": "designed"}]},
        )
        (task_dir / "design.md").write_text("# Design\n\n更新 live-api。\n", encoding="utf-8")
        (task_dir / "prd-refined.md").write_text(
            "# PRD Refined\n\n"
            "## 变更范围\n\n"
            "- 支持直播列表按国家筛选。\n\n"
            "## 验收标准\n\n"
            "- 国家筛选结果正确。\n",
            encoding="utf-8",
        )
        return task_dir

    def _create_cross_repo_plan_ready_task(self, task_root: Path, root: Path) -> Path:
        task_dir = task_root / "task-plan"
        task_dir.mkdir(parents=True)
        live_common = root / "live_common"
        live_pack = root / "live_pack"
        live_common.mkdir(parents=True)
        live_pack.mkdir(parents=True)
        self._write_json(task_dir / "input.json", {"title": "竞拍讲解卡文案"})
        self._write_json(
            task_dir / "repos.json",
            {
                "repos": [
                    {"id": "live_common", "path": str(live_common), "status": "designed"},
                    {"id": "live_pack", "path": str(live_pack), "status": "designed"},
                ]
            },
        )
        (task_dir / "design.md").write_text(
            "# Design\n\n"
            "## 分仓库方案\n\n"
            "### live_common\n"
            "- 文件修改：abtest/struct.go\n"
            "- 新增 AB 实验字段：`UseAuctionCardTextOptimization`。\n\n"
            "### live_pack\n"
            "- 文件修改：regular_auction_converter.go\n"
            "- 读取新增 AB 字段并更新文案逻辑。\n\n"
            "## 风险与待确认\n"
            "- 确认新增的 AB 字段名称与实验配置保持一致\n",
            encoding="utf-8",
        )
        (task_dir / "prd-refined.md").write_text(
            "# PRD Refined\n\n"
            "## 具体变更点\n\n"
            "- 只改竞拍讲解卡文案。\n\n"
            "## 验收标准\n\n"
            "- 命中第一个实验时展示 Starting bid。\n",
            encoding="utf-8",
        )
        return task_dir


def _write_plan_native_template(prompt: str) -> None:
    template_path = _extract_template_path(prompt)
    Path(template_path).write_text(
        "# Plan\n\n"
        "## 任务清单\n"
        "- W1: 实现国家筛选。\n\n"
        "## 执行顺序\n"
        "- W1\n\n"
        "## 验证策略\n"
        "- 检查国家筛选查询链路。\n\n"
        "## 风险与阻塞项\n"
        "- 保持现有接口兼容。\n",
        encoding="utf-8",
    )


def _extract_template_path(prompt: str) -> str:
    match = re.search(r"文件：(/.+?\.plan-[^\s]+)", prompt) or re.search(r"file: (/.+?\.plan-[^\s]+)", prompt)
    if not match:
        raise AssertionError("prompt did not include a plan template path")
    return match.group(1).strip()


if __name__ == "__main__":
    unittest.main()
