from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_sections_section, build_repo_binding_section


def build_design_verify_template_json() -> str:
    return (
        '{\n'
        '  "ok": false,\n'
        '  "issues": ["__FILL__"],\n'
        '  "reason": "__FILL__"\n'
        '}\n'
    )


def build_design_verify_agent_prompt(
    *,
    title: str,
    design_markdown: str,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Design 的校验。",
        goal="检查生成后的 design.md 是否和 repo binding、design sections 一致，并直接编辑指定 JSON 模板文件写入结果。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "重点检查章节是否齐全、是否脱离结构化结果、是否引入未出现的仓库或文件。",
            "如果存在多个 in_scope repo，必须逐个检查 design.md 是否明确交代每个 repo 的角色，而不是只写主仓。",
            "如果存在 validate_only repo，必须检查它是否被单独写进“联动验证仓库”，并解释为什么不作为主改造仓。",
            "如果 must_change repo 已给出 candidate_files 或 repo_decisions，必须检查 design.md 是否写出实现落点或候选文件。",
            "如果 design.md 只是重复 refined 需求，没有体现 repo_decisions 里的仓库现状和判定理由，必须判失败。",
            "如果 selection_basis=heuristic_tiebreak，必须检查 design.md 是否明确区分“单仓可闭合”和“默认选择哪个仓作为起始实现仓”。",
            "如果校验通过，ok=true，issues 使用空数组。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=DESIGN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。"),
            PromptSection(title="Design Markdown", body=design_markdown.strip()),
            build_repo_binding_section(repo_binding_payload),
            build_design_sections_section(sections_payload),
        ],
    )
    return render_prompt(document)
