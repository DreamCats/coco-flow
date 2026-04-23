from __future__ import annotations

import unittest

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.refine import __all__ as refine_prompt_exports
from coco_flow.prompts.refine import build_refine_generate_agent_prompt, build_refine_verify_agent_prompt


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
            ["build_refine_generate_agent_prompt", "build_refine_verify_agent_prompt"],
        )

    def test_refine_generate_prompt_is_modularized(self) -> None:
        rendered = build_refine_generate_agent_prompt(
            manual_extract_path="/tmp/refine-manual-extract.json",
            brief_draft_path="/tmp/refine-brief.draft.json",
            source_excerpt_path="/tmp/refine-source.excerpt.md",
            template_path="/tmp/refine-template.md",
        )
        self.assertIn("staff-level backend product requirements editor", rendered)
        self.assertIn("/tmp/refine-manual-extract.json", rendered)
        self.assertIn("/tmp/refine-brief.draft.json", rendered)
        self.assertIn("/tmp/refine-source.excerpt.md", rendered)
        self.assertIn("/tmp/refine-template.md", rendered)

    def test_refine_verify_prompt_is_modularized(self) -> None:
        rendered = build_refine_verify_agent_prompt(
            brief_draft_path="/tmp/refine-brief.draft.json",
            refined_markdown_path="/tmp/prd-refined.md",
            template_path="/tmp/refine-verify.json",
        )
        self.assertIn("principal-level requirements verifier", rendered)
        self.assertIn("/tmp/refine-brief.draft.json", rendered)
        self.assertIn("/tmp/prd-refined.md", rendered)
        self.assertIn("/tmp/refine-verify.json", rendered)


if __name__ == "__main__":
    unittest.main()
