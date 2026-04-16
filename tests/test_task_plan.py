from __future__ import annotations

import unittest

from coco_flow.engines.plan_models import (
    ContextSnapshot,
    DesignAISections,
    ExecutionAISections,
    PlanAISections,
    RefinedSections,
    RepoResearch,
    ResearchFinding,
)
from coco_flow.engines.plan_render import build_plan_tasks
from coco_flow.engines.plan_research import build_design_research_signals, parse_refined_sections


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
        self.assertTrue(signals.protocol_changes)
        self.assertTrue(signals.storage_config_changes)
        self.assertTrue(signals.experiment_changes)
        self.assertTrue(signals.qa_inputs)

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

    def test_build_plan_tasks_uses_repo_order_and_polished_titles(self) -> None:
        sections = RefinedSections(
            change_scope=["支持直播列表按国家筛选并保持原有排序"],
            non_goals=["不改接口协议"],
            key_constraints=[],
            acceptance_criteria=["筛选结果正确且保持原有排序"],
            open_questions=[],
            raw="",
        )
        findings = ResearchFinding(
            matched_terms=[],
            unmatched_terms=[],
            candidate_files=[
                "live-api/internal/handler/list.go",
                "live-api/internal/service/list.go",
                "live-web/src/pages/live/list.tsx",
            ],
            candidate_dirs=["internal/handler", "internal/service", "src/pages/live"],
            notes=[],
        )
        ai = PlanAISections(
            design=DesignAISections(solution_overview="- 先在 API 侧收敛筛选逻辑，再同步前端筛选入口。"),
            execution=ExecutionAISections(
                steps=(
                    "- 在 live-api/internal/handler/list.go 中补齐国家筛选入参透传\n"
                    "- 在 live-api/internal/service/list.go 中补齐国家筛选逻辑并保持原有排序\n"
                    "- 在 live-web/src/pages/live/list.tsx 中补齐筛选项展示和请求参数拼装"
                )
            ),
        )

        tasks = build_plan_tasks(sections, findings, ai, {"live-api", "live-web"}, ["live-api", "live-web"])

        self.assertEqual([task.id for task in tasks], ["T1", "T2", "T3"])
        self.assertEqual(tasks[0].title, "[live-api] 补齐国家筛选入参透传")
        self.assertEqual(tasks[1].title, "[live-api] 补齐国家筛选逻辑并保持原有排序")
        self.assertEqual(tasks[2].title, "[live-web] 补齐筛选项展示和请求参数拼装")
        self.assertEqual(tasks[1].depends_on, ["T1"])
        self.assertEqual(tasks[2].depends_on, ["T2"])
        self.assertTrue(tasks[0].actions[0].startswith("先确认仓库 live-api"))
        self.assertEqual(tasks[0].target_system_or_repo, "live-api")
        self.assertEqual(tasks[0].verify_rule, ["受影响 package 编译通过。"])
        self.assertIn("变更范围", tasks[0].actions[-1])


if __name__ == "__main__":
    unittest.main()
