from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coco_flow.config import Settings
from coco_flow.engines.plan.models import PLAN_HARNESS_VERSION, PlanExecutionGraph, PlanPreparedInput
from coco_flow.engines.plan.pipeline import run_plan_engine
from coco_flow.engines.plan.review import build_local_plan_review_payload, build_plan_decision_payload
from coco_flow.engines.plan.task_outline import build_local_plan_task_outline_payload, normalize_plan_work_items
from coco_flow.engines.shared.models import (
    ContextSnapshot,
    RefinedSections,
    RepoResearch,
    RepoScope,
    ResearchFinding,
)
from coco_flow.engines.shared.research import build_design_research_signals, parse_refined_sections


class PlanTaskBuilderTest(unittest.TestCase):
    def test_plan_result_exposes_phase_zero_harness_gate_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root)
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")

            result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, lambda _line: None)

            plan_result = result.intermediate_artifacts["plan-result.json"]
            draft = result.intermediate_artifacts["plan-draft-work-items.json"]
            draft_graph = result.intermediate_artifacts["plan-draft-execution-graph.json"]
            draft_validation = result.intermediate_artifacts["plan-draft-validation.json"]
            self.assertIsInstance(plan_result, dict)
            self.assertIsInstance(draft, dict)
            self.assertIsInstance(draft_graph, dict)
            self.assertIsInstance(draft_validation, dict)
            self.assertEqual(plan_result["harness_version"], PLAN_HARNESS_VERSION)
            self.assertEqual(plan_result["gate_status"], "passed")
            self.assertEqual(plan_result["code_allowed"], True)
            self.assertEqual(plan_result["planner_degraded"], False)
            self.assertEqual(plan_result["review_degraded"], False)
            self.assertEqual(plan_result["review_blocking_count"], 0)
            self.assertEqual(plan_result["decision_finalized"], True)
            self.assertEqual(plan_result["status"], "planned")
            self.assertEqual(draft["planner"]["source"], "local")
            self.assertEqual(draft["planner"]["degraded"], False)
            self.assertEqual(draft_graph["scheduler"]["source"], "local")
            self.assertEqual(draft_graph["scheduler"]["degraded"], False)
            self.assertEqual(draft_validation["validation_designer"]["source"], "local")
            self.assertEqual(draft_validation["validation_designer"]["degraded"], False)
            self.assertIn("plan-review.json", result.intermediate_artifacts)
            self.assertIn("plan-debate.json", result.intermediate_artifacts)
            self.assertIn("plan-decision.json", result.intermediate_artifacts)

    def test_native_planner_fallback_marks_draft_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root, plan_executor="native")
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")

            with (
                patch("coco_flow.clients.CocoACPClient.run_agent", side_effect=ValueError("native unavailable")),
                patch(
                    "coco_flow.engines.plan.review.CocoACPClient.new_agent_session",
                    side_effect=ValueError("skeptic native unavailable"),
                ),
            ):
                result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, lambda _line: None)

            plan_result = result.intermediate_artifacts["plan-result.json"]
            draft = result.intermediate_artifacts["plan-draft-work-items.json"]
            draft_graph = result.intermediate_artifacts["plan-draft-execution-graph.json"]
            draft_validation = result.intermediate_artifacts["plan-draft-validation.json"]
            self.assertIsInstance(plan_result, dict)
            self.assertIsInstance(draft, dict)
            self.assertEqual(draft["planner"]["source"], "local_fallback")
            self.assertEqual(draft["planner"]["degraded"], True)
            self.assertEqual(draft["planner"]["fallback_stage"], "planner")
            self.assertEqual(draft_graph["scheduler"]["source"], "local_fallback")
            self.assertEqual(draft_graph["scheduler"]["degraded"], True)
            self.assertEqual(draft_validation["validation_designer"]["source"], "local_fallback")
            self.assertEqual(draft_validation["validation_designer"]["degraded"], True)
            self.assertEqual(plan_result["planner_degraded"], True)
            self.assertEqual(plan_result["review_degraded"], True)
            self.assertEqual(plan_result["fallback_stage"], "planner")

    def test_plan_skeptic_blocks_missing_must_change_repo(self) -> None:
        prepared = self._prepared_input_for_plan_review()
        graph = PlanExecutionGraph(
            nodes=[],
            edges=[],
            execution_order=[],
            parallel_groups=[],
            critical_path=[],
            coordination_points=[],
        )

        review = build_local_plan_review_payload(
            prepared,
            [],
            graph,
            {"task_validations": []},
        )
        debate, decision = build_plan_decision_payload(prepared, [], graph, {"task_validations": []}, review)

        self.assertFalse(review["ok"])
        self.assertEqual(review["issues"][0]["failure_type"], "missing_must_change_repo")
        self.assertEqual(decision["finalized"], False)
        self.assertEqual(decision["review_blocking_count"], 1)
        self.assertTrue(debate["revision"]["applied"])

    def test_plan_gate_blocks_code_when_decision_not_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root)
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")
            review_payload = {
                "ok": False,
                "issues": [
                    {
                        "severity": "blocking",
                        "failure_type": "code_input_missing",
                        "target": "W1",
                        "expected": "work item 可交给 Code",
                        "actual": "缺少明确输入",
                        "suggested_action": "补齐 inputs",
                    }
                ],
            }
            def fake_review(prepared, work_items, graph, validation_payload, settings, on_log):
                decision_payload = {
                    "task_id": prepared.task_id,
                    "finalized": False,
                    "review_blocking_count": 1,
                    "review_warning_count": 0,
                    "work_items": [item.to_payload() for item in work_items],
                    "execution_graph": graph.to_payload(),
                    "validation": validation_payload,
                }
                return review_payload, {"revision": {"applied": True}}, decision_payload

            with patch(
                "coco_flow.engines.plan.pipeline.build_plan_review_and_decision",
                side_effect=fake_review,
            ):
                result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, lambda _line: None)

            plan_result = result.intermediate_artifacts["plan-result.json"]
            verify = result.intermediate_artifacts["plan-verify.json"]
            self.assertEqual(result.status, "failed")
            self.assertEqual(plan_result["gate_status"], "needs_human")
            self.assertEqual(plan_result["code_allowed"], False)
            self.assertEqual(plan_result["decision_finalized"], False)
            self.assertFalse(verify["ok"])

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

    def test_build_local_plan_work_items_follow_binding_order(self) -> None:
        prepared = PlanPreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task-1",
            title="直播列表国家筛选",
            design_markdown="# Design",
            refined_markdown="# PRD Refined",
            input_meta={},
            task_meta={},
            design_repo_binding_payload={
                "repo_bindings": [
                    {
                        "repo_id": "live-api",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "serves_change_points": [1],
                        "change_summary": ["补齐国家筛选主链路"],
                        "boundaries": ["保持现有接口兼容"],
                        "candidate_dirs": ["internal/handler"],
                        "candidate_files": [
                            "live-api/internal/handler/list.go",
                            "live-api/internal/service/list.go",
                        ],
                        "depends_on": [],
                    },
                    {
                        "repo_id": "live-web",
                        "decision": "in_scope",
                        "scope_tier": "co_change",
                        "serves_change_points": [1],
                        "change_summary": ["补齐前端筛选入口"],
                        "boundaries": ["不改接口协议"],
                        "candidate_dirs": ["src/pages/live"],
                        "candidate_files": ["live-web/src/pages/live/list.tsx"],
                        "depends_on": ["live-api"],
                    },
                ]
            },
            design_sections_payload={},
            design_result_payload={},
            repos_meta={},
            repo_scopes=[
                RepoScope(repo_id="live-api", repo_path="/tmp/live-api"),
                RepoScope(repo_id="live-web", repo_path="/tmp/live-web"),
            ],
            repo_ids={"live-api", "live-web"},
            refined_sections=RefinedSections(
                change_scope=["支持直播列表按国家筛选并保持原有排序"],
                non_goals=["不改接口协议"],
                key_constraints=[],
                acceptance_criteria=["筛选结果正确且保持原有排序"],
                open_questions=[],
                raw="",
            ),
        )

        outline_payload = build_local_plan_task_outline_payload(prepared)
        tasks = normalize_plan_work_items(outline_payload, prepared)

        self.assertEqual([task.id for task in tasks], ["W1", "W2"])
        self.assertEqual(tasks[0].repo_id, "live-api")
        self.assertEqual(tasks[1].repo_id, "live-web")
        self.assertEqual(tasks[0].title, "[live-api] 推进「支持直播列表按国家筛选并保持原有排序」执行")
        self.assertEqual(tasks[1].depends_on, ["W1"])
        self.assertTrue(tasks[0].specific_steps)
        self.assertEqual(tasks[0].change_scope[0], "live-api/internal/handler/list.go")
        self.assertIn("Design 责任保持一致", tasks[0].done_definition[-1])

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
        self._write_json(
            task_dir / "design-repo-binding.json",
            {
                "repo_bindings": [
                    {
                        "repo_id": "live-api",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                        "serves_change_points": [1],
                        "change_summary": ["补齐国家筛选主链路"],
                        "candidate_files": ["internal/handler/list.go"],
                    }
                ]
            },
        )
        self._write_json(
            task_dir / "design-sections.json",
            {"critical_flows": [{"name": "国家筛选", "trigger": "查询直播列表"}]},
        )
        self._write_json(task_dir / "design-result.json", {"gate_status": "passed", "plan_allowed": True})
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

    def _prepared_input_for_plan_review(self) -> PlanPreparedInput:
        return PlanPreparedInput(
            task_dir=Path("/tmp/task"),
            task_id="task-review",
            title="直播列表国家筛选",
            design_markdown="# Design",
            refined_markdown="# PRD Refined",
            input_meta={},
            task_meta={},
            design_repo_binding_payload={
                "repo_bindings": [
                    {
                        "repo_id": "live-api",
                        "decision": "in_scope",
                        "scope_tier": "must_change",
                    }
                ]
            },
            design_sections_payload={},
            design_result_payload={},
            repos_meta={},
            repo_scopes=[RepoScope(repo_id="live-api", repo_path="/tmp/live-api")],
            repo_ids={"live-api"},
            refined_sections=RefinedSections(
                change_scope=["支持直播列表按国家筛选"],
                non_goals=[],
                key_constraints=[],
                acceptance_criteria=["国家筛选结果正确"],
                open_questions=[],
                raw="",
            ),
        )


if __name__ == "__main__":
    unittest.main()
