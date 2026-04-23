from __future__ import annotations

import unittest

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.refine import (
    build_refine_generate_agent_prompt,
    build_refine_intent_agent_prompt,
    build_refine_intent_template_json,
    build_refine_skills_read_agent_prompt,
    build_refine_skills_read_template_markdown,
    build_refine_shortlist_agent_prompt,
    build_refine_shortlist_template_json,
    build_refine_template_markdown,
    build_refine_verify_agent_prompt,
    build_refine_verify_template_json,
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

    def test_refine_intent_prompt_contains_template_file(self) -> None:
        rendered = build_refine_intent_agent_prompt(
            title="测试需求",
            source_markdown="# PRD Source\n\n---\n\n这里是正文。",
            supplement="补充说明",
            template_path="/tmp/refine-intent.json",
        )
        self.assertIn("Refine 的意图提炼", rendered)
        self.assertIn("/tmp/refine-intent.json", rendered)
        self.assertIn("输入材料", rendered)
        self.assertIn("__FILL__", build_refine_intent_template_json())

    def test_refine_shortlist_prompt_contains_yaml_cards(self) -> None:
        rendered = build_refine_shortlist_agent_prompt(
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
            template_path="/tmp/refine-shortlist.json",
        )
        self.assertIn("候选 Skills 卡片", rendered)
        self.assertIn("```yaml", rendered)
        self.assertIn("id: k1", rendered)
        self.assertIn("__FILL__", build_refine_shortlist_template_json())

    def test_refine_template_contains_fixed_sections(self) -> None:
        rendered = build_refine_template_markdown()
        self.assertIn("# 需求确认书", rendered)
        self.assertIn("验收标准", rendered)
        self.assertIn("边界与非目标", rendered)

    def test_refine_generate_agent_prompt_points_to_template_file(self) -> None:
        rendered = build_refine_generate_agent_prompt(
            title="测试需求",
            source_markdown="# PRD Source\n\n---\n\n这里是正文。",
            supplement="补充说明",
            intent_payload={"goal": "测试目标"},
            skills_read_markdown="## 术语解释\n- 术语A",
            template_path="/tmp/prd-refined.template.md",
        )
        self.assertIn("需要编辑的模板文件", rendered)
        self.assertIn("/tmp/prd-refined.template.md", rendered)
        self.assertIn("最终文件里不能保留“待补充”或任何占位符", rendered)
        self.assertIn("“具体变更点”使用“场景：...；当前行为：...；期望行为：...”的单行结构", rendered)
        self.assertIn("“待确认项”必须使用“问题：...；当前假设：...；影响范围：...”结构", rendered)
        self.assertIn("确保最终文件可以直接作为需求确认书使用", rendered)

    def test_refine_skills_read_prompt_contains_file_cards(self) -> None:
        rendered = build_refine_skills_read_agent_prompt(
            intent_payload={"goal": "测试"},
            knowledge_documents=[
                {
                    "id": "k1",
                    "title": "知识一",
                    "kind": "flow",
                    "desc": "说明一",
                    "path": "/tmp/k1.md",
                }
            ],
            template_path="/tmp/refine-skills-read.md",
        )
        self.assertIn("已选 Skills 文件", rendered)
        self.assertIn("/tmp/k1.md", rendered)
        self.assertIn("```yaml", rendered)
        self.assertIn("待补充", build_refine_skills_read_template_markdown())

    def test_refine_verify_prompt_contains_json_result_contract(self) -> None:
        rendered = build_refine_verify_agent_prompt(
            title="测试需求",
            source_markdown="# PRD Source\n\n---\n\n这里是正文。",
            supplement="补充说明",
            refined_markdown="# PRD Refined\n\n## 核心诉求\n- ...",
            template_path="/tmp/refine-verify.json",
        )
        self.assertIn('"ok": true', rendered)
        self.assertIn("待校验结果", rendered)
        self.assertIn("__FILL__", build_refine_verify_template_json())


if __name__ == "__main__":
    unittest.main()
