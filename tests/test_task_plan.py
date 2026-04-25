from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coco_flow.clients import AgentSessionHandle
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
                    "coco_flow.engines.plan.agent_io.CocoACPClient.new_agent_session",
                    side_effect=ValueError("plan native unavailable"),
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

    def test_native_plan_roles_use_inline_bootstrap_sessions(self) -> None:
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
                    handle_id=f"handle-{role}-{len(roles)}",
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
            self.assertEqual(
                roles,
                [
                    "plan_planner",
                    "plan_scheduler",
                    "plan_validation_designer",
                    "plan_skeptic",
                    "plan_writer",
                    "plan_verify",
                ],
            )
            self.assertEqual(
                closed_roles,
                [
                    "plan_planner",
                    "plan_scheduler",
                    "plan_validation_designer",
                    "plan_skeptic",
                    "plan_verify",
                    "plan_writer",
                ],
            )
            for role in roles:
                self.assertIn(f"session_role: {role}", logs)
                self.assertIn(f"bootstrap_prompt: inline role={role}", logs)
            self.assertIn("agent_prompt_start: role=plan_skeptic stage=revision", logs)
            self.assertEqual(len(prompts), len(roles) + 1)
            self.assertEqual(sum(1 for prompt in prompts if "这是内联 bootstrap" in prompt), len(roles))

    def test_native_writer_regenerate_reuses_writer_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root, plan_executor="native")
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")
            logs: list[str] = []
            roles: list[str] = []
            prompt_records: list[tuple[str, str, str]] = []
            closed_roles: list[str] = []
            verify_calls = 0

            def fake_new_session(*, query_timeout: str, cwd: str, role: str) -> AgentSessionHandle:
                roles.append(role)
                return AgentSessionHandle(
                    handle_id=f"handle-{role}-{len(roles)}",
                    cwd=cwd,
                    mode="agent",
                    query_timeout=query_timeout,
                    role=role,
                )

            def fake_prompt_session(handle: AgentSessionHandle, prompt: str) -> str:
                nonlocal verify_calls
                prompt_records.append((handle.handle_id, handle.role, prompt))
                template_path = _extract_template_path(prompt)
                if ".plan-verify-" in template_path:
                    verify_calls += 1
                    payload = (
                        {"ok": False, "issues": ["plan.md 缺少必要章节: 验证策略"], "reason": "first verify failed"}
                        if verify_calls == 1
                        else {"ok": True, "issues": [], "reason": "second verify passed"}
                    )
                    Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                else:
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
            self.assertEqual(roles.count("plan_writer"), 1)
            self.assertEqual(roles.count("plan_verify"), 2)
            writer_records = [record for record in prompt_records if record[1] == "plan_writer"]
            self.assertEqual(len(writer_records), 2)
            self.assertEqual(writer_records[0][0], writer_records[1][0])
            self.assertIn("这是内联 bootstrap", writer_records[0][2])
            self.assertNotIn("这是内联 bootstrap", writer_records[1][2])
            self.assertIn("需要修正的问题", writer_records[1][2])
            self.assertIn("plan_regenerate_start: issue_count=1", logs)
            self.assertIn("plan_regenerate_ok: true", logs)
            self.assertEqual(closed_roles[-1], "plan_writer")

    def test_native_revision_can_reject_blocking_review_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(root, plan_executor="native")
            task_dir = self._create_plan_ready_task(settings.task_root, root / "repo")
            logs: list[str] = []

            def fake_new_session(*, query_timeout: str, cwd: str, role: str) -> AgentSessionHandle:
                return AgentSessionHandle(
                    handle_id=f"handle-{role}",
                    cwd=cwd,
                    mode="agent",
                    query_timeout=query_timeout,
                    role=role,
                )

            def fake_prompt_session(handle: AgentSessionHandle, prompt: str) -> str:
                template_path = _extract_template_path(prompt)
                if ".plan-skeptic-" in template_path:
                    payload = {
                        "ok": False,
                        "issues": [
                            {
                                "severity": "blocking",
                                "failure_type": "code_input_missing",
                                "target": "W1",
                                "expected": "work item 已有 Code 输入",
                                "actual": "误判 inputs 缺失",
                                "suggested_action": "确认现有 inputs 是否足够",
                            }
                        ],
                    }
                    Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                elif ".plan-revision-" in template_path:
                    payload = {
                        "debate": {
                            "revision": {
                                "applied": True,
                                "summary": "Revision 判断该 blocking issue 是误报。",
                                "issue_resolutions": [
                                    {
                                        "failure_type": "code_input_missing",
                                        "target": "W1",
                                        "resolution": "rejected",
                                        "reason": "W1 已包含 design-repo-binding.json 和 prd-refined.md inputs。",
                                        "decision_change": "allow_code",
                                    }
                                ],
                            }
                        },
                        "decision": {"finalized": True, "unresolved_questions": []},
                    }
                    Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                else:
                    _write_plan_native_template(prompt)
                return "ok"

            with (
                patch("coco_flow.engines.plan.agent_io.CocoACPClient.new_agent_session", side_effect=fake_new_session),
                patch("coco_flow.engines.plan.agent_io.CocoACPClient.prompt_agent_session", side_effect=fake_prompt_session),
                patch("coco_flow.engines.plan.agent_io.CocoACPClient.close_agent_session", return_value=None),
            ):
                result = run_plan_engine(task_dir, {"title": "直播列表国家筛选"}, settings, logs.append)

            plan_result = result.intermediate_artifacts["plan-result.json"]
            decision = result.intermediate_artifacts["plan-decision.json"]
            debate = result.intermediate_artifacts["plan-debate.json"]
            self.assertEqual(result.status, "planned")
            self.assertEqual(plan_result["gate_status"], "passed")
            self.assertEqual(plan_result["code_allowed"], True)
            self.assertEqual(decision["revision_source"], "native")
            self.assertEqual(decision["issue_resolutions"][0]["resolution"], "rejected")
            self.assertEqual(debate["revision"]["source"], "native")
            self.assertIn("plan_revision_mode: native", logs)

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

    def test_normalize_keeps_distinct_implementation_items_in_same_repo(self) -> None:
        prepared = self._prepared_input_for_plan_review()
        outline_payload = {
            "task_units": [
                {
                    "id": "W10",
                    "title": "[live-api] 更新普通竞拍文案",
                    "repo_id": "live-api",
                    "task_type": "implementation",
                    "serves_change_points": [1],
                    "goal": "更新普通竞拍讲解卡文案。",
                    "specific_steps": ["在 regular_auction_converter.go 中更新普通竞拍文案。"],
                    "change_scope": ["regular_auction_converter.go"],
                    "inputs": ["design-repo-binding.json"],
                    "outputs": ["普通竞拍文案逻辑"],
                    "done_definition": ["普通竞拍文案正确。"],
                    "validation_focus": ["覆盖普通竞拍文案。"],
                    "risk_notes": ["不改价格逻辑。"],
                    "depends_on": [],
                },
                {
                    "id": "W20",
                    "title": "[live-api] 更新 Surprise set 文案",
                    "repo_id": "live-api",
                    "task_type": "implementation",
                    "serves_change_points": [2],
                    "goal": "更新 Surprise set 讲解卡文案。",
                    "specific_steps": ["在 surprise_set_auction_converter.go 中更新 Surprise set 文案。"],
                    "change_scope": ["surprise_set_auction_converter.go"],
                    "inputs": ["design-repo-binding.json"],
                    "outputs": ["Surprise set 文案逻辑"],
                    "done_definition": ["Surprise set 文案正确。"],
                    "validation_focus": ["覆盖 Surprise set 文案。"],
                    "risk_notes": ["不改转换状态流转。"],
                    "depends_on": ["W10"],
                },
            ]
        }

        tasks = normalize_plan_work_items(outline_payload, prepared)

        self.assertEqual(len(tasks), 2)
        self.assertEqual([task.id for task in tasks], ["W1", "W2"])
        self.assertEqual(tasks[0].change_scope, ["regular_auction_converter.go"])
        self.assertEqual(tasks[1].change_scope, ["surprise_set_auction_converter.go"])
        self.assertEqual(tasks[1].depends_on, ["W1"])

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


def _write_plan_native_template(prompt: str) -> None:
    template_path = _extract_template_path(prompt)
    if ".plan-planner-" in template_path:
        payload = {
            "task_units": [
                {
                    "id": "W1",
                    "title": "[live-api] 实现国家筛选",
                    "repo_id": "live-api",
                    "task_type": "implementation",
                    "serves_change_points": [1],
                    "goal": "补齐国家筛选主链路。",
                    "specific_steps": ["在 internal/handler/list.go 中接入国家筛选参数。"],
                    "scope_summary": ["补齐国家筛选主链路"],
                    "inputs": ["design-repo-binding.json", "prd-refined.md"],
                    "outputs": ["live-api 国家筛选实现"],
                    "done_definition": ["国家筛选结果正确。"],
                    "validation_focus": ["覆盖国家筛选查询链路。"],
                    "risk_notes": ["保持现有接口兼容。"],
                }
            ]
        }
        Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return
    if ".plan-scheduler-" in template_path:
        payload = {
            "nodes": [{"task_id": "W1", "repo_id": "live-api", "title": "[live-api] 实现国家筛选"}],
            "edges": [],
            "execution_order": ["W1"],
            "parallel_groups": [],
            "critical_path": ["W1"],
            "coordination_points": [],
        }
        Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return
    if ".plan-validation-designer-" in template_path:
        payload = {
            "global_validation_focus": ["国家筛选结果正确"],
            "task_validations": [
                {
                    "task_id": "W1",
                    "repo_id": "live-api",
                    "checks": [{"kind": "review", "target": "internal/handler/list.go", "reason": "检查国家筛选查询链路。"}],
                    "linked_design_flows": ["国家筛选 / 查询直播列表"],
                    "non_goal_regressions": [],
                }
            ],
        }
        Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return
    if ".plan-skeptic-" in template_path:
        Path(template_path).write_text('{"ok": true, "issues": []}\n', encoding="utf-8")
        return
    if ".plan-revision-" in template_path:
        payload = {
            "debate": {
                "revision": {
                    "applied": False,
                    "summary": "Plan Skeptic 未发现 blocking issue。",
                    "issue_resolutions": [],
                }
            },
            "decision": {
                "finalized": True,
                "unresolved_questions": [],
            },
        }
        Path(template_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return
    if ".plan-template-" in template_path:
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
        return
    if ".plan-verify-" in template_path:
        Path(template_path).write_text('{"ok": true, "issues": [], "reason": "native verify passed"}\n', encoding="utf-8")
        return
    raise AssertionError(f"unknown plan template path: {template_path}")


def _extract_template_path(prompt: str) -> str:
    match = re.search(r"file: (/.+?\.plan-[^\s]+)", prompt)
    if not match:
        raise AssertionError("prompt did not include a plan template path")
    return match.group(1).strip()


if __name__ == "__main__":
    unittest.main()
