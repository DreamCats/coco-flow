from __future__ import annotations

import unittest

from coco_flow.services.task_plan import PlanAISections, RefinedSections, ResearchFinding, build_plan_tasks


class PlanTaskBuilderTest(unittest.TestCase):
    def test_build_plan_tasks_uses_repo_order_and_polished_titles(self) -> None:
        sections = RefinedSections(
            summary="补齐直播列表筛选条件",
            features=["支持直播列表按国家筛选并保持原有排序"],
            boundaries=["不改接口协议"],
            business_rules=[],
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
            steps=(
                "- 在 live-api/internal/handler/list.go 中补齐国家筛选入参透传\n"
                "- 在 live-api/internal/service/list.go 中补齐国家筛选逻辑并保持原有排序\n"
                "- 在 live-web/src/pages/live/list.tsx 中补齐筛选项展示和请求参数拼装"
            )
        )

        tasks = build_plan_tasks(sections, findings, ai, {"live-api", "live-web"}, ["live-api", "live-web"])

        self.assertEqual([task.id for task in tasks], ["T1", "T2", "T3"])
        self.assertEqual(tasks[0].title, "[live-api] 补齐国家筛选入参透传")
        self.assertEqual(tasks[1].title, "[live-api] 补齐国家筛选逻辑并保持原有排序")
        self.assertEqual(tasks[2].title, "[live-web] 补齐筛选项展示和请求参数拼装")
        self.assertEqual(tasks[1].depends_on, ["T1"])
        self.assertEqual(tasks[2].depends_on, ["T2"])
        self.assertTrue(tasks[0].actions[0].startswith("先确认仓库 live-api"))
        self.assertIn("功能点", tasks[0].actions[-1])


if __name__ == "__main__":
    unittest.main()
