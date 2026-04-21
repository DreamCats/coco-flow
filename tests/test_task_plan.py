from __future__ import annotations

import unittest
from pathlib import Path

from coco_flow.engines.plan.models import PlanPreparedInput
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


if __name__ == "__main__":
    unittest.main()
