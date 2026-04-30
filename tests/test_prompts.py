from __future__ import annotations

import unittest

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.design import __all__ as design_prompt_exports
from coco_flow.prompts.design import (
    build_architect_prompt,
    build_design_bootstrap_prompt,
    build_design_research_prompt,
    build_design_research_review_prompt,
    build_design_research_review_template_json,
    build_design_research_template_json,
    build_doc_only_design_prompt,
    build_revision_prompt,
    build_search_hints_prompt,
    build_semantic_gate_prompt,
    build_skeptic_prompt,
    build_writer_prompt,
)
from coco_flow.prompts.plan import __all__ as plan_prompt_exports
from coco_flow.prompts.plan import (
    build_doc_only_plan_prompt,
    build_plan_bootstrap_prompt,
    build_plan_planner_agent_prompt,
    build_plan_revision_prompt,
    build_plan_scheduler_agent_prompt,
    build_plan_template_markdown,
    build_plan_skeptic_prompt,
    build_plan_validation_designer_agent_prompt,
    build_plan_writer_agent_prompt,
)
from coco_flow.prompts.refine import __all__ as refine_prompt_exports
from coco_flow.prompts.refine import (
    build_refine_bootstrap_prompt,
    build_refine_generate_agent_prompt,
    build_refine_verify_agent_prompt,
)


class PromptSystemTest(unittest.TestCase):
    def test_render_prompt_keeps_stable_section_order(self) -> None:
        rendered = render_prompt(
            PromptDocument(
                intro="intro",
                goal="goal",
                requirements=["one", "two"],
                output_contract="contract",
                sections=[PromptSection(title="Section A", body="aaa"), PromptSection(title="Section B", body="bbb")],
                closing="done",
            )
        )
        self.assertIn("intro", rendered)
        self.assertIn("目标：\ngoal", rendered)
        self.assertIn("1. one", rendered)
        self.assertIn("输出契约：\ncontract", rendered)
        self.assertLess(rendered.index("Section A"), rendered.index("Section B"))

    def test_refine_prompt_package_exports_module_builders(self) -> None:
        self.assertEqual(
            refine_prompt_exports,
            [
                "build_refine_bootstrap_prompt",
                "build_refine_generate_agent_prompt",
                "build_refine_verify_agent_prompt",
            ],
        )

    def test_design_prompt_package_exports_search_hints_builder(self) -> None:
        self.assertIn("build_design_bootstrap_prompt", design_prompt_exports)
        self.assertIn("build_doc_only_design_prompt", design_prompt_exports)
        self.assertIn("build_search_hints_prompt", design_prompt_exports)
        self.assertIn("build_search_hints_template_json", design_prompt_exports)
        self.assertIn("build_design_research_prompt", design_prompt_exports)
        self.assertIn("build_design_research_review_prompt", design_prompt_exports)

    def test_design_research_prompt_targets_single_repo_and_skills_files(self) -> None:
        rendered = build_design_research_prompt(
            title="竞拍讲解卡标题增加 Auction 标识",
            refined_markdown="# PRD\n- 命中实验时标题加 Auction",
            repo_context_payload={"repo_id": "live_pack", "repo_path": "/repo/live_pack"},
            skills_index_markdown="- /skills/auction/SKILL.md",
            skills_fallback_markdown="- fallback summary",
            template_path="/tmp/research.json",
        )

        self.assertIn("本次只调研“当前 repo”", rendered)
        self.assertIn("必须先读取相关完整 skill 文件", rendered)
        self.assertIn("skill_usage.read_files", rendered)
        self.assertIn("/skills/auction/SKILL.md", rendered)
        self.assertIn("/tmp/research.json", rendered)
        self.assertIn("reference_only / not_needed", rendered)
        self.assertIn("空数组", rendered)
        self.assertIn("Research Context Engine", rendered)
        self.assertIn("复用已有实验字段还是新增字段", rendered)
        self.assertIn("合法 JSON 示例", rendered)
        self.assertIn('"candidate_files": [', rendered)
        self.assertIn('"line_end": 128', rendered)
        self.assertIn("不要把多行代码原样粘进 JSON", rendered)

    def test_design_research_template_uses_empty_optional_arrays(self) -> None:
        template = build_design_research_template_json()

        self.assertIn('"claims": []', template)
        self.assertIn('"candidate_files": []', template)
        self.assertIn('"rejected_candidates": []', template)
        self.assertIn('"repo_id": ""', template)
        self.assertIn('"summary": ""', template)
        self.assertNotIn("__FILL__", template)

    def test_design_research_review_template_uses_empty_optional_arrays(self) -> None:
        template = build_design_research_review_template_json()

        self.assertIn('"blocking_issues": []', template)
        self.assertIn('"research_instructions": []', template)
        self.assertIn('"reason": ""', template)
        self.assertNotIn("__FILL__", template)

    def test_design_research_review_prompt_requires_skill_usage_evidence(self) -> None:
        rendered = build_design_research_review_prompt(
            title="竞拍讲解卡标题增加 Auction 标识",
            refined_markdown="# PRD\n- 命中实验时标题加 Auction",
            research_payload={"repos": [{"repo_id": "live_pack", "skill_usage": {"read_files": []}}]},
            template_path="/tmp/research-review.json",
            skills_index_markdown="- /skills/auction/SKILL.md",
        )

        self.assertIn("skill_usage.read_files", rendered)
        self.assertIn("/skills/auction/SKILL.md", rendered)
        self.assertIn("redo_research", rendered)
        self.assertIn("具体 AB 参数 key", rendered)
        self.assertIn("实验 key", rendered)
        self.assertIn("repo_id", rendered)
        self.assertIn("research_status=failed", rendered)
        self.assertIn("/tmp/research-review.json", rendered)
        self.assertIn("合法 JSON 示例", rendered)
        self.assertIn('"blocking_issues": [', rendered)
        self.assertIn('"type": "missing_candidate_evidence"', rendered)

    def test_doc_only_design_prompt_requires_relative_paths(self) -> None:
        rendered = build_doc_only_design_prompt(
            title="竞拍购物袋标题",
            refined_markdown="# PRD",
            repo_scope_markdown="- live_pack",
            research_summary_markdown="- `entities/converters/title.go`",
            skills_fallback_markdown="- fallback",
            template_path="/tmp/design.md",
        )

        self.assertIn("repo 相对路径", rendered)
        self.assertIn("不要输出本机绝对路径", rendered)

    def test_plan_prompt_package_exports_bootstrap_builder(self) -> None:
        self.assertIn("build_plan_bootstrap_prompt", plan_prompt_exports)
        self.assertIn("build_doc_only_plan_prompt", plan_prompt_exports)
        self.assertIn("build_plan_planner_agent_prompt", plan_prompt_exports)
        self.assertIn("build_plan_scheduler_agent_prompt", plan_prompt_exports)
        self.assertIn("build_plan_validation_designer_agent_prompt", plan_prompt_exports)
        self.assertIn("build_plan_skeptic_prompt", plan_prompt_exports)
        self.assertIn("build_plan_revision_prompt", plan_prompt_exports)
        self.assertIn("build_plan_writer_agent_prompt", plan_prompt_exports)

    def test_plan_bootstrap_prompt_defines_open_harness_contract(self) -> None:
        rendered = build_plan_bootstrap_prompt(
            skills_index_markdown="- plan-skill: 任务拆解与验证边界规则。"
        )

        self.assertIn("coco-flow 的 Plan 阶段 agent", rendered)
        self.assertIn("Plan Open Harness", rendered)
        self.assertIn("不重新做 Design 裁决，不改代码", rendered)
        self.assertIn("Plan 阶段协议", rendered)
        self.assertIn("Artifact 契约", rendered)
        self.assertIn("角色隔离策略", rendered)
        self.assertIn("Design 边界策略", rendered)
        self.assertIn("可交给研发执行的计划文档", rendered)
        self.assertIn("`plan.md`：唯一 Plan 阶段产物", rendered)
        self.assertIn("plan-skill: 任务拆解与验证边界规则", rendered)
        self.assertNotIn("AGENT_MODE", rendered)

    def test_plan_bootstrap_prompt_can_be_inlined(self) -> None:
        rendered = build_plan_bootstrap_prompt(standalone=False)

        self.assertIn("这是内联 bootstrap", rendered)
        self.assertNotIn("收到 bootstrap 后只需简短回复已完成", rendered)

    def test_plan_template_requires_dependency_fields(self) -> None:
        rendered = build_plan_template_markdown()

        self.assertIn("depends_on", rendered)
        self.assertIn("hard_dependencies", rendered)
        self.assertIn("coordination_points", rendered)
        self.assertIn("acceptance_mapping", rendered)
        self.assertIn("blockers", rendered)

    def test_doc_only_plan_prompt_requires_dependency_contract(self) -> None:
        rendered = build_doc_only_plan_prompt(
            title="更新竞拍讲解卡",
            repo_ids=["live_common", "live_pack"],
            refined_markdown="# PRD\n- 验收标准",
            design_markdown="# Design\n- live_common -> live_pack",
            skills_fallback_markdown="- auction-plan",
            template_path="/tmp/plan.md",
        )

        self.assertIn("/tmp/plan.md", rendered)
        self.assertIn("live_common, live_pack", rendered)
        self.assertIn("hard dependency", rendered)
        self.assertIn("depends_on", rendered)
        self.assertIn("blockers", rendered)
        self.assertIn("acceptance_mapping", rendered)

    def test_plan_planner_prompt_targets_draft_work_items(self) -> None:
        rendered = build_plan_planner_agent_prompt(
            title="直播列表国家筛选",
            design_markdown="# Design",
            refined_markdown="# PRD Refined",
            skills_fallback_markdown="- plan-skill",
            repo_binding_payload={"repo_bindings": []},
            design_sections_payload={"critical_flows": []},
            template_path="/tmp/plan-draft-work-items.json",
        )

        self.assertIn("Plan Open Harness 的 Planner 角色", rendered)
        self.assertIn("plan-draft-work-items.json", rendered)
        self.assertIn("不要重新判断 repo 是否 in scope", rendered)
        self.assertIn("/tmp/plan-draft-work-items.json", rendered)

    def test_plan_scheduler_prompt_targets_draft_execution_graph(self) -> None:
        rendered = build_plan_scheduler_agent_prompt(
            title="直播列表国家筛选",
            design_markdown="# Design",
            refined_markdown="# PRD Refined",
            skills_fallback_markdown="- plan-skill",
            repo_binding_payload={"repo_bindings": []},
            work_items_payload={"work_items": []},
            template_path="/tmp/plan-draft-execution-graph.json",
        )

        self.assertIn("Plan Open Harness 的 Scheduler 角色", rendered)
        self.assertIn("plan-draft-execution-graph.json", rendered)
        self.assertIn("不要重新做 repo binding adjudication", rendered)

    def test_plan_validation_designer_prompt_targets_draft_validation(self) -> None:
        rendered = build_plan_validation_designer_agent_prompt(
            title="直播列表国家筛选",
            design_markdown="# Design",
            refined_markdown="# PRD Refined",
            skills_fallback_markdown="- plan-skill",
            work_items_payload={"work_items": []},
            execution_graph_payload={"nodes": []},
            template_path="/tmp/plan-draft-validation.json",
        )

        self.assertIn("Plan Open Harness 的 Validation Designer 角色", rendered)
        self.assertIn("plan-draft-validation.json", rendered)
        self.assertIn("每个 task_id 都必须有对应 task_validations", rendered)

    def test_plan_skeptic_prompt_reviews_structured_artifacts(self) -> None:
        rendered = build_plan_skeptic_prompt(
            title="直播列表国家筛选",
            design_markdown="# Design",
            refined_markdown="# PRD Refined",
            skills_fallback_markdown="- plan-skill",
            repo_binding_payload={"repo_bindings": []},
            work_items_payload={"work_items": []},
            execution_graph_payload={"nodes": []},
            validation_payload={"task_validations": []},
            template_path="/tmp/plan-review.json",
        )

        self.assertIn("Plan Open Harness 的 Skeptic 角色", rendered)
        self.assertIn("是否可交给 Code 阶段执行", rendered)
        self.assertIn("不得重新做 Design repo adjudication", rendered)
        self.assertIn("/tmp/plan-review.json", rendered)

    def test_plan_revision_prompt_resolves_review_issues(self) -> None:
        rendered = build_plan_revision_prompt(
            title="直播列表国家筛选",
            review_payload={
                "ok": False,
                "issues": [
                    {
                        "severity": "blocking",
                        "failure_type": "code_input_missing",
                        "target": "W1",
                        "expected": "可执行",
                        "actual": "缺少输入",
                        "suggested_action": "补齐 inputs",
                    }
                ],
            },
            work_items_payload={"work_items": []},
            execution_graph_payload={"nodes": []},
            validation_payload={"task_validations": []},
            template_path="/tmp/plan-revision.json",
        )

        self.assertIn("Skeptic/Revision session", rendered)
        self.assertIn("resolution= rejected", rendered)
        self.assertIn("resolution= needs_human", rendered)
        self.assertIn("decision.finalized 必须为 false", rendered)
        self.assertIn("/tmp/plan-revision.json", rendered)

    def test_plan_writer_prompt_consumes_plan_decision_only(self) -> None:
        rendered = build_plan_writer_agent_prompt(
            title="直播列表国家筛选",
            decision_payload={"finalized": True, "work_items": []},
            template_path="/tmp/plan.md",
        )

        self.assertIn("Plan Open Harness 的 Writer 角色", rendered)
        self.assertIn("只消费 Plan Decision", rendered)
        self.assertIn("plan-decision.json 的可读投影", rendered)
        self.assertIn("/tmp/plan.md", rendered)

    def test_design_bootstrap_prompt_defines_layered_contract(self) -> None:
        rendered = build_design_bootstrap_prompt(
            skills_index_markdown="- auction-design: 竞拍 repo role 与验收边界规则。"
        )

        self.assertIn("coco-flow 的 Design 阶段 agent", rendered)
        self.assertIn("阶段式研发 workflow 系统", rendered)
        self.assertIn("不生成 plan，不改代码", rendered)
        self.assertIn("Design 阶段协议", rendered)
        self.assertIn("Artifact 契约", rendered)
        self.assertIn("角色隔离策略", rendered)
        self.assertIn("Evidence 与 Repo 策略", rendered)
        self.assertIn("Skills 使用策略", rendered)
        self.assertIn("文件读写规则", rendered)
        self.assertIn("用户绑定的 repo 是搜索空间，不天然等于 must_change", rendered)
        self.assertIn("当前第一版不拆多角色 schema", rendered)
        self.assertIn("auction-design: 竞拍 repo role 与验收边界规则", rendered)
        self.assertNotIn("AGENT_MODE", rendered)

    def test_design_bootstrap_prompt_can_be_inlined(self) -> None:
        rendered = build_design_bootstrap_prompt(standalone=False)

        self.assertIn("这是内联 bootstrap", rendered)
        self.assertNotIn("收到 bootstrap 后只需简短回复已完成", rendered)

    def test_doc_only_design_prompt_lives_in_prompt_package(self) -> None:
        rendered = build_doc_only_design_prompt(
            title="更新竞拍讲解卡",
            refined_markdown="# PRD",
            repo_scope_markdown="- live_pack: /repo",
            research_summary_markdown="### live_pack\n- 候选文件：`a.go`",
            skills_fallback_markdown="- auction-design",
            template_path="/tmp/design.md",
        )

        self.assertIn("/tmp/design.md", rendered)
        self.assertIn("prd-refined.md", rendered)
        self.assertIn("live_pack", rendered)
        self.assertIn("Repo research summary", rendered)
        self.assertIn("不要复制 Python dict", rendered)
        self.assertIn("不能只复述核心改造点或搜索结果", rendered)
        self.assertIn("候选文件、函数名、搜索命中原因", rendered)
        self.assertIn("实验命中条件、本地化取值、空值回退", rendered)

    def test_design_role_prompts_are_task_prompts(self) -> None:
        prompts = [
            build_architect_prompt(
                title="更新竞拍讲解卡",
                refined_markdown="只改竞拍讲解卡文案。",
                skills_fallback_markdown="- auction-design",
                research_plan_payload={"repos": ["shop"]},
                research_summary_payload={"repos": [{"repo_id": "shop", "candidate_files": ["a.ts"]}]},
                template_path="/tmp/design-adjudication.json",
            ),
            build_skeptic_prompt(
                title="更新竞拍讲解卡",
                refined_markdown="只改竞拍讲解卡文案。",
                adjudication_payload={"repo_decisions": []},
                research_summary_payload={"repos": []},
                template_path="/tmp/design-review.json",
            ),
            build_revision_prompt(
                title="更新竞拍讲解卡",
                refined_markdown="只改竞拍讲解卡文案。",
                adjudication_payload={"repo_decisions": []},
                review_payload={"ok": False, "issues": []},
                research_summary_payload={"repos": []},
                template_path="/tmp/design-debate.json",
            ),
            build_writer_prompt(
                title="更新竞拍讲解卡",
                decision_payload={"finalized": True, "repo_decisions": []},
                template_path="/tmp/design.md",
            ),
            build_semantic_gate_prompt(
                title="更新竞拍讲解卡",
                refined_markdown="只改竞拍讲解卡文案。",
                decision_payload={"finalized": True},
                design_markdown="# Design",
                template_path="/tmp/design-verify.json",
            ),
        ]

        for rendered in prompts:
            self.assertIn("本次任务：", rendered)
            self.assertNotIn("AGENT_MODE", rendered)
            self.assertNotIn("你是 coco-flow Design V3", rendered)

        self.assertIn("/tmp/design-adjudication.json", prompts[0])
        self.assertIn("/tmp/design-review.json", prompts[1])
        self.assertIn("/tmp/design-debate.json", prompts[2])
        self.assertIn("/tmp/design.md", prompts[3])
        self.assertIn("/tmp/design-verify.json", prompts[4])

    def test_design_search_hints_prompt_does_not_allow_repo_reading(self) -> None:
        rendered = build_search_hints_prompt(
            title="更新成功态",
            refined_markdown="需要更新 BidSuccessToast。",
            design_skills_fallback_markdown="RegularAuctionConverter 是常见搜索线索。",
            repo_context_payload=[{"repo_id": "demo", "repo_name": "demo-repo"}],
            template_path="/tmp/search-hints.json",
        )

        self.assertIn("不要读取、遍历或推断仓库代码内容", rendered)
        self.assertIn("RegularAuctionConverter", rendered)
        self.assertIn("/tmp/search-hints.json", rendered)
        self.assertIn("BidSuccessToast", rendered)

    def test_refine_generate_prompt_is_modularized(self) -> None:
        rendered = build_refine_generate_agent_prompt(
            manual_extract_path="/tmp/refine-manual-extract.json",
            brief_draft_path="/tmp/refine-brief.draft.json",
            source_excerpt_path="/tmp/refine-source.excerpt.md",
            template_path="/tmp/refine-template.md",
        )
        self.assertIn("本次任务：基于人工提炼范围和原文片段生成需求确认书", rendered)
        self.assertNotIn("AGENT_MODE", rendered)
        self.assertIn("/tmp/refine-manual-extract.json", rendered)
        self.assertIn("/tmp/refine-brief.draft.json", rendered)
        self.assertIn("/tmp/refine-source.excerpt.md", rendered)
        self.assertIn("/tmp/refine-template.md", rendered)

    def test_refine_bootstrap_prompt_defines_layered_contract(self) -> None:
        rendered = build_refine_bootstrap_prompt(
            skills_index_markdown="- auction: 竞拍需求验收边界规则。"
        )

        self.assertIn("coco-flow 的 Refine 阶段 agent", rendered)
        self.assertIn("阶段式研发 workflow 系统", rendered)
        self.assertIn("不做技术设计、不做排期、不改代码", rendered)
        self.assertIn("具备需求编辑能力", rendered)
        self.assertIn("具备验收设计能力", rendered)
        self.assertIn("Refine 阶段协议", rendered)
        self.assertIn("Artifact 契约", rendered)
        self.assertIn("角色隔离策略", rendered)
        self.assertIn("Skills 使用策略", rendered)
        self.assertIn("文件读写规则", rendered)
        self.assertIn("人工提炼范围优先级最高", rendered)
        self.assertIn("Verify Session 不得采信 Generate Session 的口头解释", rendered)
        self.assertIn("auction: 竞拍需求验收边界规则", rendered)

    def test_refine_bootstrap_prompt_can_be_inlined(self) -> None:
        rendered = build_refine_bootstrap_prompt(standalone=False)

        self.assertIn("这是内联 bootstrap", rendered)
        self.assertNotIn("收到 bootstrap 后只需简短回复已完成", rendered)

    def test_refine_verify_prompt_is_modularized(self) -> None:
        rendered = build_refine_verify_agent_prompt(
            brief_draft_path="/tmp/refine-brief.draft.json",
            refined_markdown_path="/tmp/prd-refined.md",
            template_path="/tmp/refine-verify.json",
        )
        self.assertIn("本次任务：独立校验需求确认书是否偏离 brief draft", rendered)
        self.assertIn("不采信生成阶段的口头解释或聊天历史", rendered)
        self.assertNotIn("AGENT_MODE", rendered)
        self.assertIn("/tmp/refine-brief.draft.json", rendered)
        self.assertIn("/tmp/prd-refined.md", rendered)
        self.assertIn("/tmp/refine-verify.json", rendered)


if __name__ == "__main__":
    unittest.main()
