from __future__ import annotations

import unittest

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.refine import (
    build_refine_generate_prompt,
    build_refine_intent_prompt,
    build_refine_shortlist_prompt,
    build_refine_verify_prompt,
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

    def test_refine_intent_prompt_contains_json_contract(self) -> None:
        rendered = build_refine_intent_prompt(
            title="测试需求",
            source_markdown="# PRD Source\n\n---\n\n这里是正文。",
            supplement="补充说明",
        )
        self.assertIn("Refine 的意图提炼", rendered)
        self.assertIn('"goal"', rendered)
        self.assertIn("输入材料", rendered)

    def test_refine_shortlist_prompt_contains_yaml_cards(self) -> None:
        rendered = build_refine_shortlist_prompt(
            intent_payload={"goal": "测试", "change_points": ["A"]},
            knowledge_cards=[
                {
                    "id": "k1",
                    "title": "知识一",
                    "kind": "flow",
                    "domain_name": "测试域",
                    "desc": "说明一",
                }
            ],
        )
        self.assertIn("候选知识卡片", rendered)
        self.assertIn("```yaml", rendered)
        self.assertIn("id: k1", rendered)

    def test_refine_generate_prompt_contains_output_sections(self) -> None:
        rendered = build_refine_generate_prompt(
            title="测试需求",
            source_markdown="# PRD Source\n\n---\n\n这里是正文。",
            supplement="补充说明",
            intent_payload={"goal": "测试目标"},
            knowledge_read_markdown="## 术语解释\n- 术语A",
        )
        self.assertIn("# PRD Refined", rendered)
        self.assertIn("风险提示", rendered)
        self.assertIn("边界与非目标", rendered)

    def test_refine_verify_prompt_contains_json_result_contract(self) -> None:
        rendered = build_refine_verify_prompt(
            title="测试需求",
            source_markdown="# PRD Source\n\n---\n\n这里是正文。",
            supplement="补充说明",
            refined_markdown="# PRD Refined\n\n## 核心诉求\n- ...",
        )
        self.assertIn('"ok": true', rendered)
        self.assertIn("待校验结果", rendered)


if __name__ == "__main__":
    unittest.main()
