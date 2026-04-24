from __future__ import annotations

import unittest

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.design import __all__ as design_prompt_exports
from coco_flow.prompts.design import build_search_hints_prompt
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
        self.assertIn("build_search_hints_prompt", design_prompt_exports)
        self.assertIn("build_search_hints_template_json", design_prompt_exports)

    def test_design_search_hints_prompt_does_not_allow_repo_reading(self) -> None:
        rendered = build_search_hints_prompt(
            title="更新成功态",
            refined_markdown="需要更新 BidSuccessToast。",
            design_skills_brief_markdown="RegularAuctionConverter 是常见搜索线索。",
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
        self.assertIn("本次任务：基于 Refine artifact 生成需求确认书", rendered)
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
